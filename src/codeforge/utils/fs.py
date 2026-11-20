"""Filesystem helpers with path-traversal protection."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

IGNORED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "dist", "build", ".idea", ".vscode", ".eggs",
    ".codeforge_cache", "coverage", ".next", "target",
}


class UnsafePathError(ValueError):
    pass


def safe_relpath(rel: str) -> str:
    """Validate a repository-relative POSIX path coming from untrusted input (e.g. an LLM)."""
    rel = rel.replace("\\", "/").strip()
    if rel.startswith("./"):
        rel = rel[2:]
    p = PurePosixPath(rel)
    if not rel or not p.parts or p.is_absolute() or ".." in p.parts or rel.startswith("~") \
            or ":" in p.parts[0]:
        raise UnsafePathError(f"unsafe path: {rel!r}")
    if p.parts[0] == ".git":
        raise UnsafePathError(f"refusing to touch .git: {rel!r}")
    return str(p)


def resolve_inside(root: Path, rel: str) -> Path:
    rel = safe_relpath(rel)
    target = (root / rel).resolve()
    if not target.is_relative_to(root.resolve()):
        raise UnsafePathError(f"path escapes root: {rel!r}")
    return target


def iter_repo_files(root: Path, max_file_bytes: int = 1_000_000):
    """Yield repository files (relative POSIX paths) skipping vendored/build directories."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")
                             or d in {".github"})
        for name in sorted(filenames):
            full = Path(dirpath) / name
            try:
                if full.is_symlink() or full.stat().st_size > max_file_bytes:
                    continue
            except OSError:
                continue
            yield full.relative_to(root).as_posix()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_text_lf(path: Path, text: str, executable: bool = False) -> None:
    """Write text with LF line endings (scripts run inside Linux containers)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text.replace("\r\n", "\n"))
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _on_rm_error(func, path, _exc):  # pragma: no cover - windows read-only files
    os.chmod(path, stat.S_IWRITE)
    func(path)


def rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onexc=_on_rm_error)


def zip_dir(src: Path, dest_zip: Path) -> Path:
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(src.rglob("*")):
            if file.is_file():
                zf.write(file, Path(src.name) / file.relative_to(src))
    return dest_zip


def safe_extract_zip(zip_path: Path, dest: Path) -> None:
    """Extract an archive while rejecting absolute paths, traversal and symlinks."""
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            name = member.filename
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise UnsafePathError(f"symlink in archive: {name}")
            target = resolve_inside(dest, name.rstrip("/")) if name.rstrip("/") else dest
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(member))
