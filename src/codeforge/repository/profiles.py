"""Repository profiles: the per-ecosystem recipe for building and testing a repository.

Concept adapted from SWE-smith's profile registry (swesmith/profiles, MIT): each profile
bundles install/test knowledge so the rest of the pipeline stays repository-agnostic.
CodeForge selects a profile automatically from detected languages and manifests, and a
repository can override it with a `codeforge.toml` file (see docs/architecture.md).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from codeforge.adapters.languages.base import LanguageAdapter
from codeforge.adapters.languages.javascript_adapter import JavaScriptAdapter
from codeforge.adapters.languages.python_adapter import PythonAdapter


@dataclass(frozen=True)
class ProfileOverride:
    """Optional per-repository overrides read from `codeforge.toml` at the repository root."""

    test_dirs: list[str] | None = None
    source_dirs: list[str] | None = None
    build_command: list[str] | None = None
    python_version: str | None = None


def load_override(root: Path) -> ProfileOverride:
    path = root / "codeforge.toml"
    if not path.exists():
        return ProfileOverride()
    data = tomllib.loads(path.read_text(encoding="utf-8")).get("profile", {})
    return ProfileOverride(
        test_dirs=data.get("test_dirs"),
        source_dirs=data.get("source_dirs"),
        build_command=data.get("build_command"),
        python_version=data.get("python_version"),
    )


def adapter_for(language: str, test_framework: str | None) -> LanguageAdapter | None:
    """Profile registry lookup."""
    if language == "python" and test_framework in ("pytest", None):
        return PythonAdapter()
    if language in ("javascript", "typescript") and test_framework in (
        "node:test", "vitest", "jest"
    ):
        return JavaScriptAdapter(test_framework)
    return None


def adapter_by_name(name: str) -> LanguageAdapter | None:
    if name == PythonAdapter.name:
        return PythonAdapter()
    if name.startswith("node"):
        return JavaScriptAdapter(name.split(":", 1)[1] if ":" in name else None)
    return None
