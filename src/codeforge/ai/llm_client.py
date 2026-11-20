"""Model access through LiteLLM, with response caching and usage tracking.

Defaults keep CodeForge free to run: Gemini's free tier (GEMINI_API_KEY) with a local
Ollama model as fallback. Responses are cached by a hash of (model, prompts, temperature,
seed), so re-running a pipeline reproduces the same generation exactly. Cached and live
responses are labelled as such in the evidence; nothing is ever fabricated.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from codeforge.config import Settings, get_settings
from codeforge.logging_config import redact

log = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    text: str
    model: str
    purpose: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_sec: float = 0.0
    cached: bool = False
    cache_key: str = ""


@dataclass
class UsageTracker:
    calls: int = 0
    cached_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    by_purpose: dict[str, int] = field(default_factory=dict)
    models: set[str] = field(default_factory=set)

    def add(self, r: LLMResponse) -> None:
        self.calls += 1
        self.cached_calls += int(r.cached)
        self.prompt_tokens += r.prompt_tokens
        self.completion_tokens += r.completion_tokens
        self.by_purpose[r.purpose] = self.by_purpose.get(r.purpose, 0) + 1
        self.models.add(r.model)

    def as_dict(self) -> dict:
        return {"calls": self.calls, "cached_calls": self.cached_calls,
                "prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens,
                "by_purpose": self.by_purpose, "models": sorted(self.models)}


class LLMError(RuntimeError):
    pass


class ChatModel(Protocol):
    usage: UsageTracker

    def complete(self, system: str, user: str, purpose: str, json_mode: bool = True
                 ) -> LLMResponse: ...


class LLMClient:
    def __init__(self, settings: Settings | None = None, model: str | None = None):
        self.s = settings or get_settings()
        self.model = model or self.s.model
        self.usage = UsageTracker()
        self.cache_dir = self.s.cache_dir / "llm"

    def _key(self, model: str, system: str, user: str) -> str:
        material = json.dumps([model, system, user, self.s.temperature, self.s.seed])
        return hashlib.sha256(material.encode()).hexdigest()

    def _cache_get(self, key: str) -> dict | None:
        path = self.cache_dir / f"{key}.json"
        if self.s.llm_cache and path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def _cache_put(self, key: str, payload: dict) -> None:
        if not self.s.llm_cache:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")

    def complete(self, system: str, user: str, purpose: str, json_mode: bool = True
                 ) -> LLMResponse:
        models = [self.model] + [m for m in self.s.fallback_models if m != self.model]
        # Replay a cached response from any model first (exact reproduction of a past run).
        for model in models:
            key = self._key(model, system, user)
            hit = self._cache_get(key)
            if hit:
                r = LLMResponse(hit["text"], model, purpose, hit.get("prompt_tokens", 0),
                                hit.get("completion_tokens", 0), 0.0, True, key)
                self.usage.add(r)
                return r
        exhausted = self._exhausted_today()
        last_error: Exception | None = None
        for model in models:
            if model in exhausted:
                continue
            key = self._key(model, system, user)
            r = None
            for attempt in range(3):  # small backoff for per-minute free-tier limits
                try:
                    r = self._call(model, system, user, purpose, json_mode)
                    break
                except Exception as exc:  # provider errors, rate limits, timeouts
                    last_error = exc
                    full = str(exc)
                    msg = redact(full)[:240].replace("\n", " ")
                    log.warning("model %s failed for %s (try %d): %s", model, purpose,
                                attempt + 1, msg)
                    if "PerDay" in full or "per day" in full.lower():
                        self._mark_exhausted(model)
                        break
                    transient = any(k in full.lower() for k in ("429", "rate limit", "503",
                                                                "overloaded", "timeout",
                                                                "unavailable", "500"))
                    if not transient:
                        break
                    time.sleep(15 * (attempt + 1))
            if r is None:
                continue
            r.cache_key = key
            self._cache_put(key, {"text": r.text, "model": model, "purpose": purpose,
                                  "prompt_tokens": r.prompt_tokens,
                                  "completion_tokens": r.completion_tokens,
                                  "created": time.time()})
            self.usage.add(r)
            return r
        raise LLMError(f"all models failed for {purpose}: {redact(str(last_error))[:500]}")

    def _exhausted_path(self) -> Path:
        return self.cache_dir / "exhausted_models.json"

    @staticmethod
    def quota_day() -> str:
        """The Gemini free-tier quota day. Quotas reset at midnight Pacific time, so the key
        is the Pacific date (UTC-8; during daylight time this releases one hour late, which
        errs on the safe side). Windows Pythons often lack tz data, hence a fixed offset."""
        return time.strftime("%Y-%m-%d", time.gmtime(time.time() - 8 * 3600))

    def _exhausted_today(self) -> set[str]:
        path = self._exhausted_path()
        if not path.exists():
            return set()
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get(self.quota_day(), []))

    def _mark_exhausted(self, model: str) -> None:
        """Remember that a model hit its free daily quota until the Pacific-midnight reset."""
        path = self._exhausted_path()
        day = self.quota_day()
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        data = {day: sorted(set(data.get(day, [])) | {model})}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        log.warning("model %s reached its free daily quota; skipping it today", model)

    def _call(self, model: str, system: str, user: str, purpose: str, json_mode: bool
              ) -> LLMResponse:
        import litellm  # imported lazily: slow import, optional for analysis-only use

        litellm.suppress_debug_info = True
        kwargs: dict = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_tokens": self.s.max_output_tokens,
            "timeout": self.s.llm_timeout_sec,
        }
        if self.s.reasoning_effort and model.startswith("gemini/"):
            kwargs["reasoning_effort"] = self.s.reasoning_effort
        if not model.startswith("gemini/"):
            # Gemini 3 deprecates sampling parameters; other providers still honour them.
            kwargs["temperature"] = self.s.temperature
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        start = time.monotonic()
        resp = litellm.completion(**kwargs)
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text, model=model, purpose=purpose,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_sec=round(time.monotonic() - start, 2),
        )


class ScriptedLLM:
    """Test double that returns pre-written responses per purpose. Used ONLY in CodeForge's
    own unit tests; never wired into the pipeline's real runs."""

    def __init__(self, responses: dict[str, list[str]]):
        self.responses = {k: list(v) for k, v in responses.items()}
        self.usage = UsageTracker()
        self.prompts: list[tuple[str, str, str]] = []

    def complete(self, system: str, user: str, purpose: str, json_mode: bool = True
                 ) -> LLMResponse:
        self.prompts.append((purpose, system, user))
        queue = self.responses.get(purpose)
        if not queue:
            raise LLMError(f"no scripted response for {purpose}")
        r = LLMResponse(queue.pop(0) if len(queue) > 1 else queue[0], "scripted", purpose)
        self.usage.add(r)
        return r


def provider_status(settings: Settings | None = None) -> dict:
    """Report which free providers are configured, without revealing secrets."""
    import os
    import shutil

    s = settings or get_settings()
    return {
        "model": s.model,
        "fallbacks": s.fallback_models,
        "gemini_key_present": bool(os.environ.get("GEMINI_API_KEY")),
        "ollama_installed": bool(shutil.which("ollama") or
                                 Path.home().joinpath("AppData/Local/Programs/Ollama").exists()),
    }
