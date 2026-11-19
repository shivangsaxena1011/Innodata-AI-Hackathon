"""Tree-sitter parser registry (py-tree-sitter >= 0.25 API: Language, Parser, Query, QueryCursor)."""

from __future__ import annotations

import logging
from functools import lru_cache
from importlib import resources

import tree_sitter as ts

log = logging.getLogger(__name__)


def _load_language(lang: str) -> ts.Language | None:
    try:
        if lang == "python":
            import tree_sitter_python as mod
        elif lang == "javascript":
            import tree_sitter_javascript as mod
        else:
            return None
    except ImportError:  # pragma: no cover - optional grammar not installed
        return None
    return ts.Language(mod.language())


@lru_cache(maxsize=None)
def get_language(lang: str) -> ts.Language | None:
    return _load_language(lang)


@lru_cache(maxsize=None)
def get_parser(lang: str) -> ts.Parser | None:
    language = get_language(lang)
    return ts.Parser(language) if language else None


@lru_cache(maxsize=None)
def get_tags_query(lang: str) -> ts.Query | None:
    """Load the vendored `<lang>-tags.scm` query (see THIRD_PARTY_NOTICES.md)."""
    language = get_language(lang)
    if not language:
        return None
    try:
        text = resources.files("codeforge.repository.queries").joinpath(f"{lang}-tags.scm")
        source = text.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        return None
    try:
        return ts.Query(language, source)
    except ts.QueryError as exc:  # pragma: no cover - guarded by unit tests
        log.warning("tags query for %s failed to compile: %s", lang, exc)
        return None


def supported_languages() -> list[str]:
    return [lang for lang in ("python", "javascript") if get_language(lang)]


def parse(lang: str, source: bytes) -> ts.Tree | None:
    parser = get_parser(lang)
    return parser.parse(source) if parser else None


def run_query(query: ts.Query, node: ts.Node) -> dict[str, list[ts.Node]]:
    return ts.QueryCursor(query).captures(node)
