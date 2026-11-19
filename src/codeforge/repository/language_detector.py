"""Language detection by file extension, weighted by line count."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

EXTENSIONS: dict[str, str] = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".java": "java", ".kt": "kotlin", ".go": "go", ".rs": "rust", ".rb": "ruby",
    ".php": "php", ".cs": "csharp", ".cpp": "cpp", ".cc": "cpp", ".c": "c", ".h": "c",
    ".swift": "swift", ".scala": "scala",
}

TEST_HINTS = ("test_", "_test.", ".test.", ".spec.", "/tests/", "/test/", "/__tests__/", "conftest")


def language_of(path: str) -> str | None:
    return EXTENSIONS.get(Path(path).suffix.lower())


def is_test_path(path: str) -> bool:
    p = "/" + path.lower()
    name = p.rsplit("/", 1)[-1]
    return any(h in p for h in TEST_HINTS) or name.startswith("test")


def detect_languages(root: Path, files: list[str]) -> dict[str, int]:
    """Return {language: source line count}, largest first."""
    counts: Counter[str] = Counter()
    for rel in files:
        lang = language_of(rel)
        if not lang:
            continue
        try:
            counts[lang] += sum(1 for _ in open(root / rel, encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return dict(counts.most_common())
