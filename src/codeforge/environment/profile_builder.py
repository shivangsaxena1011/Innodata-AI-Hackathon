"""Turn a RepositoryProfile into a reproducible Docker environment (SWE-smith-style
repository-to-environment step, adapted for Harbor task environments)."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from codeforge.adapters.languages.base import LanguageAdapter
from codeforge.environment.docker_builder import DockerSandbox
from codeforge.schemas.repository import RepositoryProfile
from codeforge.utils import fs

log = logging.getLogger(__name__)

DOCKERIGNORE = "**/.git\n**/__pycache__\n**/*.pyc\n**/.pytest_cache\n**/node_modules\n"


@dataclass
class EnvironmentSpec:
    env_dir: Path          # Docker build context: Dockerfile + repo/
    image_tag: str
    base_image: str        # pinned with a digest
    dockerfile: str


def image_tag_for(profile: RepositoryProfile) -> str:
    return f"codeforge-env/{profile.repository_name}:{profile.starting_commit_sha[:12]}"


def write_environment(
    profile: RepositoryProfile,
    snapshot_dir: Path,
    env_dir: Path,
    adapter: LanguageAdapter,
    pinned_base: str,
) -> EnvironmentSpec:
    """Write `env_dir/Dockerfile` and copy the pristine snapshot to `env_dir/repo/`.
    The snapshot carries no `.git`, so the image has no history to mine for shortcuts."""
    fs.rmtree(env_dir)
    env_dir.mkdir(parents=True)
    shutil.copytree(snapshot_dir, env_dir / "repo",
                    ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".pytest_cache",
                                                  "node_modules", ".codeforge_cache"))
    dockerfile = adapter.dockerfile(profile, pinned_base)
    fs.write_text_lf(env_dir / "Dockerfile", dockerfile)
    fs.write_text_lf(env_dir / ".dockerignore", DOCKERIGNORE)
    return EnvironmentSpec(env_dir, image_tag_for(profile), pinned_base, dockerfile)


def build_environment(
    profile: RepositoryProfile,
    snapshot_dir: Path,
    env_dir: Path,
    adapter: LanguageAdapter,
    sandbox: DockerSandbox,
    log_dir: Path,
    rebuild: bool = False,
) -> EnvironmentSpec:
    sandbox.require()
    pinned = sandbox.pin_image(adapter.base_image(profile))
    spec = write_environment(profile, snapshot_dir, env_dir, adapter, pinned)
    if rebuild or not sandbox.image_exists(spec.image_tag):
        log.info("building %s from %s", spec.image_tag, pinned)
        sandbox.build(env_dir, spec.image_tag, log_path=log_dir / "docker_build.log")
    return spec
