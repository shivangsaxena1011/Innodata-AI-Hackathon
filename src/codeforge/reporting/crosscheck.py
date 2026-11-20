"""Cross-task validation from shipped Harbor packages alone (no pipeline state needed).

For N packages built from the same repository commit, run every task's hidden feature tests
against every task's reference solution (N x N cells) in the Docker sandbox:
- diagonal cells must PASS (each reference satisfies its own tests);
- off-diagonal cells should FAIL (tests of task i do not accept task j's solution),
  which is executed evidence that the tasks exercise different behaviour.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from codeforge.environment.docker_builder import DockerSandbox
from codeforge.repository import profiles
from codeforge.validation.test_runner import MutantOverlay, TestPlan, execute

_HEREDOC = re.compile(r"base64 -d > (\S+) <<'(CODEFORGE_EOF_\d+)'\n(.*?)\n\2", re.S)


def reference_files(task_dir: Path) -> dict[str, str]:
    """Decode the reference file contents embedded in solution/solve.sh."""
    sh = (task_dir / "solution" / "solve.sh").read_text(encoding="utf-8")
    files = {}
    for path, _tag, body in _HEREDOC.findall(sh):
        files[path.strip("'\"")] = base64.b64decode(body.replace("\n", "")).decode("utf-8")
    return files


def feature_tests(task_dir: Path) -> dict[str, str]:
    root = task_dir / "tests" / "feature"
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(root.rglob("*")) if p.is_file()}


def _env_digest(task_dir: Path) -> str:
    h = hashlib.sha256()
    env = task_dir / "environment"
    for p in sorted(env.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(env).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def crosscheck(task_dirs: list[Path], out_dir: Path, sandbox: DockerSandbox | None = None
               ) -> dict:
    sandbox = sandbox or DockerSandbox()
    sandbox.require()
    manifests = [json.loads((d / "task_manifest.json").read_text(encoding="utf-8"))
                 for d in task_dirs]
    if any(m["repository"]["language"] != "python" for m in manifests):
        raise ValueError("cross-check currently supports Python packages")
    adapter = profiles.adapter_by_name("python-pytest")
    assert adapter is not None

    # Row i runs in task i's own environment (the repository its tests belong to). Packages
    # that share an identical environment share one image.
    images: dict[str, str] = {}
    row_image = []
    for d, m in zip(task_dirs, manifests, strict=True):
        digest = _env_digest(d)
        if digest not in images:
            tag = f"codeforge-pkg/{m['repository']['name']}:{digest}"
            if not sandbox.image_exists(tag):
                sandbox.build(d / "environment", tag,
                              log_path=out_dir / f"build-{m['repository']['name']}.log")
            images[digest] = tag
        row_image.append(images[digest])
    repos = [m["repository"]["name"] for m in manifests]
    commits = {m["repository"]["starting_commit_sha"] for m in manifests}

    refs = [reference_files(d) for d in task_dirs]
    tests = [feature_tests(d) for d in task_dirs]
    ids = [m["task_id"] for m in manifests]
    cells: list[list[dict]] = []
    for i, tests_i in enumerate(tests):
        plan = TestPlan(feature_tests=tests_i, mutant_test_paths=list(tests_i),
                        mutants=[MutantOverlay(f"r{j}", ref) for j, ref in enumerate(refs)],
                        stop_on_first_failure_for_mutants=False)
        res = execute(plan, adapter, row_image[i], sandbox, out_dir / f"tests-{i}",
                      timeout=180 * len(refs) + 120)
        row = []
        for j in range(len(refs)):
            run = res.mutant_runs[f"r{j}"]
            errors = [e for e in run.errors if not e.startswith("<")]
            missing = [e for e in run.errors if e.startswith("<")]
            ok = bool(run.passed) and not run.failed and not errors and not missing
            row.append({"tests_of": ids[i], "reference_of": ids[j],
                        "same_repository": repos[i] == repos[j],
                        "environment_image": row_image[i],
                        "result": "pass" if ok else "fail", "passed": len(run.passed),
                        "failed": len(run.failed), "errors": len(errors) + len(missing),
                        "expected": "pass" if i == j else "fail"})
        cells.append(row)

    n = len(ids)
    diag_ok = all(cells[i][i]["result"] == "pass" for i in range(n))
    off = [cells[i][j] for i in range(n) for j in range(n) if i != j]
    off_fail = sum(c["result"] == "fail" for c in off)
    same = [c for c in off if c["same_repository"]]
    cross = [c for c in off if not c["same_repository"]]
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "repository": repos[0] if len(set(repos)) == 1 else sorted(set(repos)),
        "starting_commit_sha": next(iter(commits)) if len(commits) == 1 else sorted(commits),
        "environment_image": row_image[0] if len(images) == 1 else sorted(images.values()),
        "tasks": [{"index": k, "task_id": ids[k], "title": manifests[k]["title"],
                   "archetype": manifests[k]["archetype"], "repository": repos[k],
                   "starting_commit_sha": manifests[k]["repository"]["starting_commit_sha"]}
                  for k in range(n)],
        "matrix": [[c["result"] for c in row] for row in cells],
        "cells": [c for row in cells for c in row],
        "diagonal_pass": f"{sum(cells[i][i]['result'] == 'pass' for i in range(n))}/{n}",
        "off_diagonal_fail": f"{off_fail}/{len(off)}",
        "same_repository_off_diagonal_fail":
            f"{sum(c['result'] == 'fail' for c in same)}/{len(same)}",
        "cross_repository_off_diagonal_fail":
            f"{sum(c['result'] == 'fail' for c in cross)}/{len(cross)}",
        "all_expectations_met": diag_ok and off_fail == len(off),
        "note": "Computed only from the shipped Harbor packages: tests from tests/feature, "
                "reference files decoded from solution/solve.sh, environment from environment/. "
                "Row i runs in task i's own environment. Same-repository cells measure "
                "behavioural discrimination; cross-repository cells only show that a task's "
                "tests still fail when another repository's reference is applied.",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    return result
