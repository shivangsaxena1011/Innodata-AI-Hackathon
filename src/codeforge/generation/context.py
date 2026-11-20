"""Select and format repository source context for generation prompts."""

from __future__ import annotations

from pathlib import Path

from codeforge.repository.language_detector import is_test_path, language_of
from codeforge.schemas.repository import RepositoryProfile


def relevant_files(profile: RepositoryProfile, hinted: list[str], limit: int = 6) -> list[str]:
    rm = profile.repository_map
    known = {f.path for f in rm.files} if rm else set()
    picked = [f for f in hinted if f in known and not is_test_path(f)]
    # Add direct dependencies of the hinted files (files they reference).
    if rm:
        for a, b in rm.dependency_edges:
            if a in picked and b not in picked and not is_test_path(b):
                picked.append(b)
        for f in profile.important_files:
            if f not in picked:
                picked.append(f)
    return picked[:limit]


def format_sources(root: Path, files: list[str], max_chars: int = 60_000,
                   overlay: dict[str, str] | None = None) -> str:
    parts, used = [], 0
    for rel in files:
        if overlay and rel in overlay:
            text = overlay[rel]
        else:
            path = root / rel
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        lang = language_of(rel) or ""
        block = f"### {rel}\n```{lang}\n{text}\n```\n"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts) or "(no source available)"


def example_test(root: Path, profile: RepositoryProfile, max_chars: int = 3000) -> str:
    rm = profile.repository_map
    tests = [f.path for f in (rm.files if rm else []) if f.is_test and
             not f.path.endswith("conftest.py")]
    if not tests:
        return "(no existing tests)"
    best = max(tests, key=lambda p: (root / p).stat().st_size if (root / p).exists() else 0)
    text = (root / best).read_text(encoding="utf-8", errors="replace")[:max_chars]
    out = f"### {best}\n```\n{text}\n```"
    # Fixtures show how the existing suite constructs domain objects.
    for f in (rm.files if rm else []):
        if f.path.endswith("conftest.py") and (root / f.path).exists():
            fx = (root / f.path).read_text(encoding="utf-8", errors="replace")[:max_chars]
            out += f"\n\n### {f.path} (fixtures: copy their construction logic, do not use " \
                   f"them directly)\n```\n{fx}\n```"
            break
    return out
