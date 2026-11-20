"""Cross-task discrimination matrix: run task i's hidden tests against task j's reference.

Diagonal cells must pass (each reference satisfies its own tests). Off-diagonal cells should
fail: if task i's tests also pass with task j's reference, the two tasks are not testing
different behaviour. This is executed evidence of meaningful variation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from codeforge.environment.docker_builder import DockerSandbox
from codeforge.schemas.task import GeneratedTask
from codeforge.validation.test_runner import MutantOverlay, TestPlan, execute

if TYPE_CHECKING:
    from codeforge.pipeline import RepoContext


def discrimination_matrix(tasks: list[GeneratedTask], ctx: RepoContext,
                          sandbox: DockerSandbox) -> dict:
    ids = [t.task_id for t in tasks]
    cells: list[list[str]] = []
    for i, ti in enumerate(tasks):
        tests = {f.path: f.content for f in ti.feature_test_files}
        overlays = [MutantOverlay(f"r{j}", {c.path: c.content for c in tj.reference.changes})
                    for j, tj in enumerate(tasks)]
        plan = TestPlan(feature_tests=tests, mutants=overlays, mutant_test_paths=list(tests),
                        stop_on_first_failure_for_mutants=False)
        res = execute(plan, ctx.adapter, ctx.env.image_tag, sandbox,
                      ctx.run_dir / "variation" / f"tests-of-{i}",
                      timeout=180 * len(tasks) + 120)
        row = []
        for j in range(len(tasks)):
            run = res.mutant_runs[f"r{j}"]
            ok = bool(run.passed) and not run.failed and not \
                [e for e in run.errors if not e.startswith("<")]
            row.append("pass" if ok else "fail")
        cells.append(row)
    n = len(tasks)
    diagonal_ok = all(cells[i][i] == "pass" for i in range(n))
    off = [(i, j) for i in range(n) for j in range(n) if i != j]
    discriminating = sum(1 for i, j in off if cells[i][j] == "fail")
    return {"tasks": ids, "cells": cells, "diagonal_all_pass": diagonal_ok,
            "off_diagonal_fail": discriminating, "off_diagonal_total": len(off),
            "discrimination_rate": round(discriminating / len(off), 3) if off else None}
