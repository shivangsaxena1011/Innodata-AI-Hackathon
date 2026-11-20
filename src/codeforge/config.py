"""Runtime configuration loaded from environment variables and an optional .env file.

Secrets (model API keys) are never stored in source code. LiteLLM reads provider keys
such as GEMINI_API_KEY directly from the environment.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CODEFORGE_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Model provider (free by default: Gemini free tier, Ollama as a fully local fallback).
    model: str = "gemini/gemini-flash-latest"
    # Gemini's free tier limits requests per model per day, so CodeForge rotates through
    # several free Flash models before falling back to a local Ollama model.
    fallback_models: list[str] = Field(
        default_factory=lambda: [
            "gemini/gemini-3.5-flash", "gemini/gemini-2.5-flash", "gemini/gemini-3.6-flash",
            "gemini/gemini-3.7-flash", "gemini/gemini-3-flash-preview",
            "gemini/gemini-3.1-flash-lite", "gemini/gemini-2.5-flash-lite", "ollama/llama3.2",
        ]
    )
    temperature: float = 0.2
    reasoning_effort: str | None = "low"  # Gemini thinking budget: low | medium | high
    max_output_tokens: int = 16000
    llm_timeout_sec: int = 240
    llm_cache: bool = True

    # Paths
    workspace_dir: Path = PROJECT_ROOT / "workspace"
    output_dir: Path = PROJECT_ROOT / "generated_tasks"
    reports_dir: Path = PROJECT_ROOT / "reports"
    cache_dir: Path = PROJECT_ROOT / ".codeforge_cache"

    # Execution sandbox
    docker_bin: str = "docker"
    harbor_bin: str = ""  # auto-detected when empty
    container_memory: str = "2g"
    container_cpus: str = "2"
    container_pids: int = 512
    test_timeout_sec: int = 600
    build_timeout_sec: int = 900
    max_repo_mb: int = 200

    # Generation policy
    seed: int = 1337
    candidates_per_round: int = 6
    max_repair_attempts: int = 2
    strengthen_rounds: int = 1  # surviving mutants -> extra hidden tests (adopted if better)
    max_mutants: int = 30
    min_mutation_score: float = 0.6
    baseline_runs: int = 3
    novelty_threshold: float = 0.55
    harbor_org: str = "codeforge"


def load_dotenv(path: Path | None = None) -> list[str]:
    """Export KEY=VALUE lines from `.env` into os.environ without overriding variables that
    are already set. LiteLLM and Harbor's agents read provider keys (e.g. GEMINI_API_KEY)
    from the process environment, which pydantic-settings does not populate.
    Returns the variable NAMES that were loaded (never their values)."""
    import os

    path = path or PROJECT_ROOT / ".env"
    if not path.exists():
        return []
    loaded = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if not key.isidentifier() or not value or value.startswith("your_"):
            continue  # skip blanks and placeholders from .env.example
        if key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    return Settings()
