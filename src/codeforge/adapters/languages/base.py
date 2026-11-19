"""Language adapter interface. An adapter knows how to build, test and mutate one ecosystem.

Generated reference code and tests always use the target repository's own language and
test framework; CodeForge itself stays in Python.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from codeforge.schemas.repository import RepositoryProfile


class LanguageAdapter(ABC):
    name: str = "base"
    language: str = "unknown"
    supports_ast_mutation: bool = False

    @abstractmethod
    def dockerfile(self, profile: RepositoryProfile, base_image: str) -> str:
        """Dockerfile for the task environment (expects the repo copied from `repo/`)."""

    @abstractmethod
    def base_image(self, profile: RepositoryProfile) -> str:
        """Unpinned base image reference; the environment builder pins it to a digest."""

    @abstractmethod
    def test_shell(self, test_paths: list[str], junit_path: str) -> str:
        """A bash command line (run in /app) that executes tests and writes JUnit XML."""

    @abstractmethod
    def feature_test_path(self, profile: RepositoryProfile, slug: str) -> str:
        """Repository-relative path where the hidden feature test file is installed."""

    def regression_paths(self, profile: RepositoryProfile) -> list[str]:
        return profile.test_dirs or ["."]

    def test_style_hint(self, profile: RepositoryProfile) -> str:
        return f"Use {profile.test_framework or 'the repository test framework'}."
