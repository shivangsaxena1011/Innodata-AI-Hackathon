"""Build a RepositoryProfile: languages, frameworks, dependencies, tests and a ranked map."""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from codeforge.repository import language_detector, profiles
from codeforge.repository.dependency_analyzer import analyze_dependencies
from codeforge.repository.git_manager import RepoCheckout
from codeforge.repository.repo_mapper import RepoMapper
from codeforge.schemas.repository import RepositoryProfile
from codeforge.utils.fs import iter_repo_files

log = logging.getLogger(__name__)


def _top_dirs(files: list[str], predicate) -> list[str]:
    counts: Counter[str] = Counter()
    for f in files:
        if predicate(f) and "/" in f:
            counts[f.split("/", 1)[0]] += 1
    return [d for d, _ in counts.most_common(5)]


def profile_repository(
    checkout: RepoCheckout, cache_dir: Path | None = None, token_budget: int = 2500
) -> RepositoryProfile:
    root = checkout.snapshot_dir
    files = list(iter_repo_files(root))
    languages = language_detector.detect_languages(root, files)
    primary = next(iter(languages), "unknown")
    deps = analyze_dependencies(root, files, primary)
    override = profiles.load_override(root)

    src_files = [f for f in files if language_detector.language_of(f) == primary]
    test_dirs = override.test_dirs or _top_dirs(src_files, language_detector.is_test_path)
    source_dirs = override.source_dirs or _top_dirs(
        src_files, lambda f: not language_detector.is_test_path(f))

    build_cmd = override.build_command or []
    if primary == "python" and not build_cmd and deps.installable_project:
        build_cmd = ["pip", "install", "-e", "."]

    adapter = profiles.adapter_for(primary, deps.test_framework)
    profile = RepositoryProfile(
        repository_name=checkout.name,
        repository_url=checkout.url,
        local_path=str(checkout.repo_dir),
        starting_commit_sha=checkout.sha,
        branch=checkout.branch,
        primary_language=primary,
        detected_languages=languages,
        framework=deps.framework,
        runtime_version=override.python_version or deps.runtime_version,
        package_manager=deps.package_manager,
        dependency_files=deps.manifests,
        test_framework=deps.test_framework,
        build_command=build_cmd,
        test_dirs=test_dirs,
        source_dirs=source_dirs,
        adapter=adapter.name if adapter else "unsupported",
        supported=adapter is not None,
        unsupported_reason=None if adapter else (
            f"no execution adapter for language={primary!r} test_framework="
            f"{deps.test_framework!r}; analysis is still available"),
    )
    if adapter:
        profile.test_command = ["bash", "-lc", adapter.test_shell(test_dirs, "/cf/out/junit.xml")]

    mapper = RepoMapper(cache_dir)
    profile.repository_map = mapper.build(root, files, checkout.sha, token_budget=token_budget)
    rank = profile.repository_map.file_rank
    profile.important_files = [f for f in rank if not language_detector.is_test_path(f)][:10]
    return profile
