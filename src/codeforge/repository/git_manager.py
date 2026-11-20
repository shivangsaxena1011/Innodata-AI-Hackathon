"""Git input handling: clone or open a repository, pin the exact commit, and export a
pristine snapshot. The original repository is never modified."""

from __future__ import annotations

import logging
import os
import re
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from codeforge.schemas.repository import DirtyPolicy
from codeforge.utils import fs
from codeforge.utils.proc import CommandError, run

log = logging.getLogger(__name__)

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_URL_RE = re.compile(r"^(https://|git@|ssh://)[\w.@:/\-~]+$")

# Fixed identity/date make the sample repository's commit SHA reproducible on every machine.
_DETERMINISTIC_ENV = {
    "GIT_AUTHOR_NAME": "CodeForge Sample",
    "GIT_AUTHOR_EMAIL": "sample@codeforge.invalid",
    "GIT_COMMITTER_NAME": "CodeForge Sample",
    "GIT_COMMITTER_EMAIL": "sample@codeforge.invalid",
    "GIT_AUTHOR_DATE": "2026-11-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-11-01T00:00:00+00:00",
}


class RepositoryError(RuntimeError):
    pass


@dataclass
class RepoCheckout:
    name: str
    url: str
    repo_dir: Path        # git repository (clone or user's local repo; read-only for us)
    sha: str              # full 40-char commit SHA, the immutable identity
    branch: str | None
    snapshot_dir: Path    # exported tree at `sha`, no .git, safe to build from
    dirty_files: list[str]


def _git(args: list[str], cwd: Path, env: dict | None = None, timeout: float = 300) -> str:
    full_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})}
    result = run(["git", "-c", "core.autocrlf=false", *args], cwd=cwd, env=full_env,
                 timeout=timeout)
    if not result.ok:
        raise CommandError(result, f"git {args[0]} failed")
    return result.stdout.strip()


def repo_name_from(source: str) -> str:
    name = source.replace("\\", "/").rstrip("/").split("/")[-1].split(":")[-1]
    name = name.removesuffix(".git") or "repository"
    return re.sub(r"[^A-Za-z0-9_.-]", "-", name).lower()


def is_remote(source: str) -> bool:
    return bool(_URL_RE.match(source))


def materialize_sample(sample_dir: Path, dest: Path) -> Path:
    """Turn a plain sample directory into a git repository with a deterministic commit."""
    if (dest / ".git").exists():
        return dest
    fs.rmtree(dest)
    shutil.copytree(sample_dir, dest, ignore=shutil.ignore_patterns(*fs.IGNORED_DIRS))
    _git(["init", "-q", "-b", "main"], dest)
    _git(["add", "-A"], dest)
    _git(["commit", "-q", "-m", "shopcart 1.4.0"], dest, env=_DETERMINISTIC_ENV)
    return dest


def _dirty_files(repo_dir: Path) -> list[str]:
    out = _git(["status", "--porcelain", "--untracked-files=normal"], repo_dir)
    return [line[3:] for line in out.splitlines() if line.strip()]


def checkout(
    source: str,
    workspace: Path,
    ref: str | None = None,
    dirty_policy: DirtyPolicy = DirtyPolicy.REFUSE,
    max_repo_mb: int = 200,
) -> RepoCheckout:
    """Resolve `source` (URL or local path) at `ref` to an exact SHA and export a snapshot."""
    workspace.mkdir(parents=True, exist_ok=True)
    name = repo_name_from(source)
    if is_remote(source):
        repo_dir = workspace / "repos" / name
        if not (repo_dir / ".git").exists():
            fs.rmtree(repo_dir)
            repo_dir.parent.mkdir(parents=True, exist_ok=True)
            _git(["clone", "-q", "--no-tags", source, str(repo_dir)], workspace, timeout=900)
        else:
            _git(["fetch", "-q", "origin"], repo_dir, timeout=900)
        url = source
    else:
        repo_dir = Path(source).expanduser().resolve()
        if not (repo_dir / ".git").exists():
            raise RepositoryError(f"{repo_dir} is not a git repository")
        try:
            url = _git(["config", "--get", "remote.origin.url"], repo_dir)
        except CommandError:
            url = repo_dir.as_uri()

    dirty = _dirty_files(repo_dir)
    target = ref or "HEAD"
    if dirty and not is_remote(source):
        if dirty_policy is DirtyPolicy.REFUSE:
            raise RepositoryError(
                f"repository has {len(dirty)} uncommitted change(s); commit them or choose "
                f"a dirty policy (use_head / commit_snapshot). First: {dirty[:5]}"
            )
        if dirty_policy is DirtyPolicy.COMMIT_SNAPSHOT:
            target = _snapshot_commit(repo_dir)
            log.warning("snapshotted %d dirty files as synthetic commit %s", len(dirty), target)

    sha = _git(["rev-parse", "--verify", f"{target}^{{commit}}"], repo_dir)
    if not _SHA_RE.match(sha):
        raise RepositoryError(f"could not resolve {target!r} to a commit SHA")
    try:
        branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], repo_dir)
        branch = None if branch == "HEAD" else branch
    except CommandError:
        branch = None

    size_kb = int(_git(["count-objects", "-v"], repo_dir).split("size-pack:")[-1].split()[0])
    if size_kb / 1024 > max_repo_mb:
        raise RepositoryError(f"repository pack is {size_kb // 1024} MB (> {max_repo_mb} MB limit)")

    snapshot_dir = workspace / "snapshots" / f"{name}-{sha[:12]}"
    if not snapshot_dir.exists():
        export_tree(repo_dir, sha, snapshot_dir)
    return RepoCheckout(name, url, repo_dir, sha, branch, snapshot_dir, dirty)


def _snapshot_commit(repo_dir: Path) -> str:
    """Create a commit object for the working tree without touching branches or the index."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index"), **_DETERMINISTIC_ENV}
        _git(["read-tree", "HEAD"], repo_dir, env=env)
        _git(["add", "-A"], repo_dir, env=env)
        tree = _git(["write-tree"], repo_dir, env=env)
        return _git(["commit-tree", tree, "-p", "HEAD", "-m", "codeforge dirty snapshot"],
                    repo_dir, env=env)


def export_tree(repo_dir: Path, sha: str, dest: Path) -> None:
    """Export the tree at `sha` with `git archive` and extract it safely (no .git, no links)."""
    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / "tree.tar"
        _git(["archive", "--format=tar", "-o", str(tar_path), sha], repo_dir)
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tar_path) as tar:
            tar.extractall(dest, filter="data")
