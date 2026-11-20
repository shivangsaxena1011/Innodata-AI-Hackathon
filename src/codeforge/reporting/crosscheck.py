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
    commits = {m["repository"]["starting_commit_sha"] for m in manifests}
    if len(commits) != 1:
        raise ValueError(f"packages come from different commits: {sorted(commits)}")
    digests = {_env_digest(d) for d in task_dirs}
    if len(digests) != 1:
        raise ValueError("packages have different environments; cross-checking needs one")
    adapter = profiles.adapter_by_name("python-pytest") \
        if manifests[0]["repository"]["language"] == "python" else None
    if adapter is None:
        raise ValueError("cross-check currently supports Python packages")

    tag = f"codeforge-pkg/{manifests[0]['repository']['name']}:{next(iter(digests))}"
    if not sandbox.image_exists(tag):
        sandbox.build(task_dirs[0] / "environment", tag, log_path=out_dir / "build.log")

    refs = [reference_files(d) for d in task_dirs]
    tests = [feature_tests(d) for d in task_dirs]
    ids = [m["task_id"] for m in manifests]
    cells: list[list[dict]] = []
    for i, tests_i in enumerate(tests):
        plan = TestPlan(feature_tests=tests_i, mutant_test_paths=list(tests_i),
                        mutants=[MutantOverlay(f"r{j}", ref) for j, ref in enumerate(refs)],
                        stop_on_first_failure_for_mutants=False)
        res = execute(plan, adapter, tag, sandbox, out_dir / f"tests-{i}",
                      timeout=180 * len(refs) + 120)
        row = []
        for j in range(len(refs)):
            run = res.mutant_runs[f"r{j}"]
            errors = [e for e in run.errors if not e.startswith("<")]
            missing = [e for e in run.errors if e.startswith("<")]
            ok = bool(run.passed) and not run.failed and not errors and not missing
            row.append({"tests_of": ids[i], "reference_of": ids[j],
                        "result": "pass" if ok else "fail", "passed": len(run.passed),
                        "failed": len(run.failed), "errors": len(errors) + len(missing),
                        "expected": "pass" if i == j else "fail"})
        cells.append(row)

    n = len(ids)
    diag_ok = all(cells[i][i]["result"] == "pass" for i in range(n))
    off = [cells[i][j] for i in range(n) for j in range(n) if i != j]
    off_fail = sum(c["result"] == "fail" for c in off)
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "repository": manifests[0]["repository"]["name"],
        "starting_commit_sha": next(iter(commits)),
        "environment_image": tag,
        "tasks": [{"index": k, "task_id": ids[k], "title": manifests[k]["title"],
                   "archetype": manifests[k]["archetype"]} for k in range(n)],
        "matrix": [[c["result"] for c in row] for row in cells],
        "cells": [c for row in cells for c in row],
        "diagonal_pass": f"{sum(cells[i][i]['result'] == 'pass' for i in range(n))}/{n}",
        "off_diagonal_fail": f"{off_fail}/{len(off)}",
        "all_expectations_met": diag_ok and off_fail == len(off),
        "note": "Computed only from the shipped Harbor packages: tests from tests/feature, "
                "reference files decoded from solution/solve.sh, environment from environment/.",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    return result
