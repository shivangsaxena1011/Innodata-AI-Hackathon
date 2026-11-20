"""Run test plans inside the Docker sandbox and parse JUnit results.

A plan stages files into the container under /cf:
  /cf/regression/  pristine copies of the repository's original tests (restored first)
  /cf/files/       file overlays (a reference solution or a mutant)
  /cf/feature/     hidden feature tests at their repository-relative paths
  /cf/mutants/<id> per-mutant file overlays, each run and then reverted
"""

from __future__ import annotations

import json
import logging
import shlex
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from codeforge.adapters.languages.base import LanguageAdapter
from codeforge.adapters.testing.junit import parse_junit
from codeforge.environment.docker_builder import DockerSandbox
from codeforge.schemas.validation import TestRun
from codeforge.utils import fs

log = logging.getLogger(__name__)


@dataclass
class TestStep:
    __test__ = False
    label: str
    test_paths: list[str]
    timeout_sec: int = 300
    shell: str | None = None  # custom command (e.g. coverage); default uses the adapter


@dataclass
class MutantOverlay:
    mutant_id: str
    files: dict[str, str]  # repo-relative path -> full mutated content


@dataclass
class TestPlan:
    __test__ = False
    overlay: dict[str, str] = field(default_factory=dict)          # path -> content
    feature_tests: dict[str, str] = field(default_factory=dict)    # path -> content
    restore_tests: dict[str, str] = field(default_factory=dict)    # path -> pristine content
    steps: list[TestStep] = field(default_factory=list)
    mutants: list[MutantOverlay] = field(default_factory=list)
    mutant_test_paths: list[str] = field(default_factory=list)
    stop_on_first_failure_for_mutants: bool = True


def _stage(root: Path, sub: str, files: dict[str, str]) -> None:
    for rel, content in files.items():
        fs.write_text_lf(fs.resolve_inside(root / sub, rel), content)


def build_script(plan: TestPlan, adapter: LanguageAdapter) -> str:
    q = shlex.quote
    lines = ["#!/bin/bash", "set -u", "cd /app", "mkdir -p /cf/out"]
    if plan.restore_tests:
        lines.append("cp -r /cf/regression/. /app/")
    if plan.overlay:
        lines.append("cp -r /cf/files/. /app/")
    if plan.feature_tests:
        lines.append("cp -r /cf/feature/. /app/")
    for step in plan.steps:
        junit = f"/cf/out/{step.label}.xml"
        cmd = step.shell or adapter.test_shell(step.test_paths, junit)
        lines.append(f"timeout {step.timeout_sec} bash -c {q(cmd)} > /cf/out/{step.label}.log 2>&1;"
                     f" echo $? > /cf/out/{step.label}.exit")
    if plan.mutants:
        lines.append("mkdir -p /tmp/cfbak")
        for m in plan.mutants:
            mid = m.mutant_id
            junit = f"/cf/out/mutant-{mid}.xml"
            extra = "-x " if plan.stop_on_first_failure_for_mutants and \
                adapter.language == "python" else ""
            cmd = adapter.test_shell(plan.mutant_test_paths, junit).replace(
                "python -m pytest ", f"python -m pytest {extra}", 1)
            for rel in m.files:
                lines.append(f"mkdir -p /tmp/cfbak/$(dirname {q(rel)}) && "
                             f"cp {q(rel)} /tmp/cfbak/{q(rel)} 2>/dev/null || true")
            lines.append(f"cp -r /cf/mutants/{mid}/. /app/")
            lines.append(f"timeout 120 bash -c {q(cmd)} > /cf/out/mutant-{mid}.log 2>&1;"
                         f" echo $? > /cf/out/mutant-{mid}.exit")
            for rel in m.files:
                lines.append(f"if [ -f /tmp/cfbak/{q(rel)} ]; then cp /tmp/cfbak/{q(rel)} {q(rel)};"
                             f" else rm -f {q(rel)}; fi")
    lines.append("echo done > /cf/out/complete")
    return "\n".join(lines) + "\n"


@dataclass
class PlanResult:
    runs: dict[str, TestRun]
    mutant_runs: dict[str, TestRun]
    out_dir: Path
    container_log: Path
    completed: bool


def execute(
    plan: TestPlan,
    adapter: LanguageAdapter,
    image: str,
    sandbox: DockerSandbox,
    out_dir: Path,
    timeout: int = 1800,
) -> PlanResult:
    with tempfile.TemporaryDirectory(prefix="codeforge-stage-") as tmp:
        stage = Path(tmp)
        _stage(stage, "regression", plan.restore_tests)
        _stage(stage, "files", plan.overlay)
        _stage(stage, "feature", plan.feature_tests)
        for m in plan.mutants:
            _stage(stage, f"mutants/{m.mutant_id}", m.files)
        script = build_script(plan, adapter)
        fs.rmtree(out_dir)
        sb = sandbox.run_script(image, stage, script, out_dir, timeout=timeout)
    runs = {s.label: _collect(out_dir, s.label, s.test_paths) for s in plan.steps}
    mutant_runs = {m.mutant_id: _collect(out_dir, f"mutant-{m.mutant_id}", plan.mutant_test_paths)
                   for m in plan.mutants}
    completed = (out_dir / "complete").exists()
    (out_dir / "summary.json").write_text(json.dumps(
        {k: v.model_dump() for k, v in runs.items()}, indent=2), encoding="utf-8")
    return PlanResult(runs, mutant_runs, out_dir, sb.container_log, completed and not
                      sb.result.timed_out)


def _collect(out_dir: Path, label: str, paths: list[str]) -> TestRun:
    junit = parse_junit(out_dir / f"{label}.xml")
    exit_file = out_dir / f"{label}.exit"
    code = int(exit_file.read_text().strip() or -1) if exit_file.exists() else None
    errors = list(junit.errors)
    if junit.parse_error:
        errors.append(f"<{junit.parse_error}>")
    return TestRun(
        label=label, command=paths, passed=junit.passed, failed=junit.failed, errors=errors,
        skipped=junit.skipped, exit_code=code, log_path=str(out_dir / f"{label}.log"),
        timed_out=code == 124, failure_text=junit.failure_text,
    )
