"""Apply SEARCH/REPLACE edits to an in-memory copy of the repository and produce file
changes plus a unified diff. The original repository and its snapshot are never modified.

The edit format follows Aider's SEARCH/REPLACE convention (Apache-2.0, idea only); matching
is exact first, then tolerant of trailing whitespace and indentation drift.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from codeforge.repository.language_detector import is_test_path
from codeforge.schemas.task import FileChange, FileEdit
from codeforge.utils.fs import resolve_inside, safe_relpath, sha256_bytes


class EditError(ValueError):
    pass


@dataclass
class Worktree:
    """A copy-on-write view of the snapshot: reads fall through to disk, writes stay in memory."""

    root: Path
    changes: dict[str, str] = field(default_factory=dict)

    def read(self, rel: str) -> str | None:
        rel = safe_relpath(rel)
        if rel in self.changes:
            return self.changes[rel]
        path = resolve_inside(self.root, rel)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def original(self, rel: str) -> str | None:
        path = resolve_inside(self.root, safe_relpath(rel))
        return path.read_text(encoding="utf-8") if path.exists() else None

    def fork(self) -> Worktree:
        return Worktree(self.root, dict(self.changes))


def _fuzzy_replace(content: str, search: str, replace: str) -> str | None:
    """Match ignoring trailing whitespace, then ignoring leading indentation uniformly."""
    c_lines = content.split("\n")
    s_lines = search.strip("\n").split("\n")
    n = len(s_lines)
    norm = [line.rstrip() for line in s_lines]
    for i in range(len(c_lines) - n + 1):
        window = c_lines[i:i + n]
        if [w.rstrip() for w in window] == norm:
            return "\n".join(c_lines[:i] + replace.strip("\n").split("\n") + c_lines[i + n:])
    stripped = [line.strip() for line in s_lines]
    for i in range(len(c_lines) - n + 1):
        window = c_lines[i:i + n]
        if [w.strip() for w in window] == stripped:
            first = window[0]
            indent = first[: len(first) - len(first.lstrip())]
            s_indent = s_lines[0][: len(s_lines[0]) - len(s_lines[0].lstrip())]
            repl = []
            for line in replace.strip("\n").split("\n"):
                repl.append(indent + line[len(s_indent):] if line.startswith(s_indent) else line)
            return "\n".join(c_lines[:i] + repl + c_lines[i + n:])
    return None


def apply_edits(tree: Worktree, edits: list[FileEdit], allow_tests: bool = False) -> list[str]:
    """Apply edits in order. Returns the touched paths. Raises EditError with a precise
    diagnosis when an edit cannot be applied (fed back to the repair loop)."""
    touched = []
    for i, edit in enumerate(edits):
        rel = safe_relpath(edit.path)
        if not allow_tests and is_test_path(rel):
            raise EditError(f"edit {i}: refusing to modify test file {rel}")
        current = tree.read(rel)
        if not edit.search.strip():
            if current is not None and current.strip():
                raise EditError(f"edit {i}: empty search for existing file {rel}; provide the "
                                f"exact text to replace")
            tree.changes[rel] = edit.replace if edit.replace.endswith("\n") else edit.replace + "\n"
        else:
            if current is None:
                raise EditError(f"edit {i}: file {rel} does not exist")
            count = current.count(edit.search)
            if count == 1:
                tree.changes[rel] = current.replace(edit.search, edit.replace, 1)
            elif count > 1:
                raise EditError(f"edit {i}: search text occurs {count} times in {rel}; "
                                f"include more context")
            else:
                fuzzy = _fuzzy_replace(current, edit.search, edit.replace)
                if fuzzy is None:
                    raise EditError(f"edit {i}: search text not found in {rel}:\n"
                                    f"{edit.search[:400]}")
                tree.changes[rel] = fuzzy
        touched.append(rel)
    return touched


def to_file_changes(tree: Worktree) -> list[FileChange]:
    out = []
    for rel in sorted(tree.changes):
        before = tree.original(rel)
        if before == tree.changes[rel]:
            continue
        out.append(FileChange(
            path=rel, action="modify" if before is not None else "create",
            before_sha256=sha256_bytes(before.encode()) if before is not None else None,
            content=tree.changes[rel],
        ))
    return out


def unified_diff(tree: Worktree, changes: list[FileChange]) -> str:
    chunks = []
    for ch in changes:
        before = tree.original(ch.path) or ""
        a = f"a/{ch.path}" if ch.action == "modify" else "/dev/null"
        chunks.extend(difflib.unified_diff(
            before.splitlines(keepends=True), ch.content.splitlines(keepends=True),
            fromfile=a, tofile=f"b/{ch.path}"))
    return "".join(chunks)


def changed_lines(before: str | None, after: str) -> set[int]:
    """1-based line numbers in `after` that were added or modified."""
    if before is None:
        return set(range(1, after.count("\n") + 2))
    lines: set[int] = set()
    sm = difflib.SequenceMatcher(a=before.splitlines(), b=after.splitlines(), autojunk=False)
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "insert"):
            lines.update(range(j1 + 1, j2 + 1))
    return lines
