"""Baseline validation of a repository environment (SWE-Gym lesson: environments are the
bottleneck, so prove the environment is healthy and stable before generating tasks).

Runs the original test suite N times on the unmodified repository, records per-test
results, and classifies tests whose outcome changes between runs as flaky. Flaky tests
are excluded from regression gates. Also checks the image for evaluation shortcuts.
"""

from __future__ import annotations

import logging
from pathlib import Path

from codeforge.adapters.languages.base import LanguageAdapter
from codeforge.environment.docker_builder import DockerSandbox
from codeforge.schemas.repository import BaselineResult, RepositoryProfile
from codeforge.validation.test_runner import TestPlan, TestStep, execute

log = logging.getLogger(__name__)


def run_baseline(
    profile: RepositoryProfile,
    adapter: LanguageAdapter,
    image: str,
    sandbox: DockerSandbox,
    out_dir: Path,
    runs: int = 3,
) -> BaselineResult:
    paths = adapter.regression_paths(profile)
    plan = TestPlan(steps=[TestStep(f"baseline-{i + 1}", paths, 900) for i in range(runs)])
    result = execute(plan, adapter, image, sandbox, out_dir, timeout=900 * runs + 120)
    outcomes: dict[str, set[str]] = {}
    duration = 0.0
    for run in result.runs.values():
        for tid in run.passed:
            outcomes.setdefault(tid, set()).add("pass")
        for tid in run.failed + run.errors:
            if not tid.startswith("<"):
                outcomes.setdefault(tid, set()).add("fail")
        duration += run.duration_sec
    passed = sorted(t for t, o in outcomes.items() if o == {"pass"})
    failed = sorted(t for t, o in outcomes.items() if o == {"fail"})
    flaky = sorted(t for t, o in outcomes.items() if len(o) > 1)
    notes = []
    any_missing = [r.label for r in result.runs.values()
                   if any(e.startswith("<") for e in r.errors)]
    if any_missing:
        notes.append(f"no junit report from: {any_missing}")
    if failed:
        notes.append(f"{len(failed)} pre-existing failing test(s) excluded from regression gates")
    if flaky:
        notes.append(f"{len(flaky)} flaky test(s) excluded from regression gates")
    healthy = bool(passed) and not any_missing and result.completed
    return BaselineResult(
        runs=runs, command=paths, passed=passed, failed=failed, flaky=flaky,
        duration_sec=duration, healthy=healthy, notes=notes,
    )


def check_image_for_shortcuts(image: str, sandbox: DockerSandbox, out_dir: Path) -> list[str]:
    """Return a list of problems found in the agent-visible image (empty means clean)."""
    script = (
        "#!/bin/bash\nmkdir -p /cf/out\n"
        "{ [ -e /app/.git ] && echo 'git-history-present';"
        "  [ -e /solution ] && echo 'solution-dir-present';"
        "  [ -e /tests ] && echo 'tests-dir-present';"
        "  ls /app | grep -qi codeforge && echo 'codeforge-artifact-in-repo';"
        "  find /app -name 'test_codeforge_*' | grep -q . && echo 'hidden-test-in-image';"
        "  env | grep -Ei '(api_key|token|secret)=' | grep -q . && echo 'secret-env-present';"
        "  true; } > /cf/out/problems.txt\n"
    )
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        sandbox.run_script(image, Path(tmp), script, out_dir, timeout=120)
    problems_file = out_dir / "problems.txt"
    if not problems_file.exists():
        return ["shortcut-check-did-not-run"]
    return [p for p in problems_file.read_text().split() if p]
