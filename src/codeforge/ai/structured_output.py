"""Parse model output into validated Pydantic models, re-asking with the validation error
when the output is malformed. Free-form model text is never used unvalidated."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from codeforge.ai.llm_client import ChatModel, LLMResponse

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class StructuredOutputError(RuntimeError):
    def __init__(self, message: str, attempts: list[dict]):
        super().__init__(message)
        self.attempts = attempts


@dataclass
class StructuredResult[T]:
    value: T
    responses: list[LLMResponse] = field(default_factory=list)
    attempts: list[dict] = field(default_factory=list)


def extract_json(text: str) -> object:
    """Extract the first JSON object from model text (tolerates ``` fences and preambles)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object found in model output")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start: i + 1])
    raise ValueError("unterminated JSON object in model output")


def generate[T: BaseModel](
    llm: ChatModel,
    model_cls: type[T],
    system: str,
    user: str,
    purpose: str,
    retries: int = 2,
) -> StructuredResult[T]:
    attempts: list[dict] = []
    responses: list[LLMResponse] = []
    prompt = user
    for attempt in range(retries + 1):
        resp = llm.complete(system, prompt, purpose=purpose if attempt == 0 else
                            f"{purpose}#retry{attempt}")
        responses.append(resp)
        try:
            data = extract_json(resp.text)
            value = model_cls.model_validate(data)
            attempts.append({"attempt": attempt, "ok": True, "cached": resp.cached})
            return StructuredResult(value, responses, attempts)
        except (ValueError, ValidationError) as exc:
            err = str(exc)[:1500]
            attempts.append({"attempt": attempt, "ok": False, "error": err})
            log.warning("%s: invalid structured output (attempt %d): %s", purpose, attempt,
                        err[:200])
            prompt = (
                f"{user}\n\n---\nYour previous reply could not be used because it failed "
                f"validation:\n{err}\nReply again with ONLY one corrected JSON object that "
                f"matches the requested schema."
            )
    raise StructuredOutputError(f"{purpose}: no valid output after {retries + 1} attempts",
                                attempts)
