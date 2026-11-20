"""Load prompt templates from the top-level `prompts/` directory.

Templates use `$name` placeholders (string.Template) so JSON examples need no escaping.
Each rendered prompt's hash is recorded in task metadata for reproducibility.
"""

from __future__ import annotations

import hashlib
from functools import cache
from pathlib import Path
from string import Template

from codeforge.config import PROJECT_ROOT

PROMPT_DIR = PROJECT_ROOT / "prompts"

SYSTEM = (
    "You are a principal software engineer who designs realistic, precisely specified "
    "feature-development tasks used to evaluate AI coding agents. You read real code "
    "carefully, never invent APIs that do not exist in the repository, and always answer "
    "with a single JSON object that matches the requested schema exactly."
)


@cache
def _template(name: str) -> Template:
    return Template((PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8"))


def render(name: str, **values: object) -> str:
    return _template(name).substitute({k: str(v) for k, v in values.items()})


def prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def available() -> list[str]:
    return sorted(p.stem for p in Path(PROMPT_DIR).glob("*.txt"))
