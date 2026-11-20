"""Three-stage validation engine (baseline -> negative control -> positive control) plus
regression, stability, mutation and coverage gates. Every verdict comes from executing
tests inside Docker; nothing is inferred from model output."""

from __future__ import annotations

import json
import logging
import shlex
from dataclasses import dataclass
from pathlib import Path

from codeforge.adapters.languages.base import LanguageAdapter
from codeforge.environment.docker_builder import DockerSandbox
from codeforge.generation.patch_generator import changed_lines
from codeforge.repository.language_detector import is_test_path, language_of
from codeforge.schemas.repository import BaselineResult
from codeforge.schemas.task import ReferenceSolution, TestFile
from codeforge.schemas.validation import (
    GateName,
    GateResult,
    GateStatus,
    MutantOutcome,
    MutationResult,
    TestRun,
)
from codeforge.validation.mutation_validator import generate_mutants
from codeforge.validation.test_runner import MutantOverlay, TestPlan, TestStep, execute

log = logging.getLogger(__name__)

COVERAGE_PIN = "coverage==7.17.3"


@dataclass
class ValidationContext:
    adapter: LanguageAdapter
    image: str               # agent/task environment image
    validation_image: str    # image + validation tools (coverage); may equal `image`
    sandbox: DockerSandbox
    baseline: BaselineResult
    regression_paths: list[str]
    out_dir: Path
    max_mutants: int = 30
    seed: int = 1337


def build_validation_image(sandbox: DockerSandbox, image: str, work_dir: Path,
                           language: str) -> str:
    """Derive a validation-only image with coverage tooling. The agent never sees it."""
    if language != "python":
        return image
    tag = image.replace("codeforge-env/", "codeforge-val/")
    if sandbox.image_exists(tag):
        return tag
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "Dockerfile").write_text(
        f"FROM {image}\nRUN pip install --no-cache-dir {COVERAGE_PIN}\n", encoding="utf-8")
    try:
        sandbox.build(work_dir, tag, log_path=work_dir / "build.log")
        return tag
    except Exception as exc:  # coverage is optional evidence
        log.warning("validation image build failed, coverage disabled: %s", exc)
        return image


def _all_feature_ids(*runs: TestRun) -> set[str]:
    ids: set[str] = set()
    for r in runs:
        ids.update(r.passed + r.failed + [e for e in r.errors if not e.startswith("<")])
    return ids


def run_controls(
    ctx: ValidationContext,
    feature_tests: list[TestFile],
    reference: ReferenceSolution,
    originals: dict[str, str | None],
    label: str,
) -> dict:
    """Run negative and positive controls. Returns raw runs plus gate results."""
    tests = {t.path: t.content for t in feature_tests}
    feature_paths = list(tests)
    overlay = {c.path: c.content for c in reference.changes}
    out = ctx.out_dir / label

    neg = execute(TestPlan(feature_tests=tests, steps=[
        TestStep("feature_original", feature_paths),
        TestStep("regression_original", ctx.regression_paths, 900),
    ]), ctx.adapter, ctx.image, ctx.sandbox, out / "negative")

    cov_files = [c.path for c in reference.changes
                 if language_of(c.path) == "python" and not is_test_path(c.path)]
    pos_steps = [
        TestStep("feature_reference_1", feature_paths),
        TestStep("regression_reference", ctx.regression_paths, 900),
        TestStep("feature_reference_2", feature_paths),
        TestStep("feature_reference_3", feature_paths),
    ]
    if cov_files and ctx.validation_image != ctx.image:
        include = ",".join(cov_files)
        pytest_cmd = ctx.adapter.test_shell(feature_paths, "/cf/out/coverage_junit.xml") \
            .replace("python -m pytest", "python -m coverage run --include="
                     + shlex.quote(include) + " -m pytest", 1)
        pos_steps.append(TestStep("coverage", feature_paths, 300, shell=(
            f"{pytest_cmd}; python -m coverage json -o /cf/out/coverage.json")))
    pos = execute(TestPlan(overlay=overlay, feature_tests=tests, steps=pos_steps),
                  ctx.adapter, ctx.validation_image, ctx.sandbox, out / "positive")

    f_neg = neg.runs["feature_original"]
    f_pos = [pos.runs[f"feature_reference_{i}"] for i in (1, 2, 3)]
    reg_pos = pos.runs["regression_reference"]
    reg_neg = neg.runs["regression_original"]
    feature_ids = sorted(_all_feature_ids(*f_pos))

    gates: list[GateResult] = []
    # Positive control: every feature test passes with the reference, none skipped.
    p1 = f_pos[0]
    pos_ok = bool(p1.passed) and not p1.failed and not p1.errors and not p1.skipped \
        and not p1.timed_out
    gates.append(GateResult(
        gate=GateName.POSITIVE_CONTROL,
        status=GateStatus.PASSED if pos_ok else GateStatus.FAILED,
        summary=f"{len(p1.passed)}/{p1.total} feature tests pass with the reference"
                + (f"; {len(p1.skipped)} skipped" if p1.skipped else ""),
        details={"passed": p1.passed, "failed": p1.failed, "errors": p1.errors,
                 "skipped": p1.skipped}, log_paths=[p1.log_path or ""]))
    # Negative control: no feature test passes on the original code.
    passing_on_original = sorted(set(f_neg.passed) & set(feature_ids))
    collection_error = any(e.startswith("<") for e in f_neg.errors) or (
        not f_neg.passed and not f_neg.failed and bool(f_neg.errors))
    neg_ok = bool(feature_ids) and not passing_on_original
    gates.append(GateResult(
        gate=GateName.NEGATIVE_CONTROL,
        status=GateStatus.PASSED if neg_ok else GateStatus.FAILED,
        summary=(f"{len(feature_ids) - len(passing_on_original)}/{len(feature_ids)} feature tests "
                 f"fail on the original code" + (" (module import fails: the contract does not "
                                                 "exist yet)" if collection_error else "")),
        details={"passing_on_original": passing_on_original, "failed": f_neg.failed,
                 "errors": f_neg.errors, "collection_error": collection_error},
        log_paths=[f_neg.log_path or ""]))
    # Regression: baseline-passing tests (minus flaky) keep passing with the reference.
    p2p = set(ctx.baseline.passed) - set(ctx.baseline.flaky)
    broken = sorted(p2p - set(reg_pos.passed))
    broken_by_tests_alone = sorted(p2p - set(reg_neg.passed))
    reg_ok = bool(p2p) and not broken
    gates.append(GateResult(
        gate=GateName.REGRESSION,
        status=GateStatus.PASSED if reg_ok else GateStatus.FAILED,
        summary=f"{len(p2p) - len(broken)}/{len(p2p)} original tests still pass with the reference",
        details={"broken": broken, "broken_by_adding_tests": broken_by_tests_alone,
                 "pass_to_pass": sorted(p2p)}, log_paths=[reg_pos.log_path or ""]))
    # Stability: repeated reference runs give identical results.
    sets = [tuple(sorted(r.passed)) for r in f_pos]
    stable = len(set(sets)) == 1 and pos_ok
    gates.append(GateResult(
        gate=GateName.STABILITY,
        status=GateStatus.PASSED if stable else GateStatus.FAILED,
        summary="3/3 reference runs identical" if len(set(sets)) == 1 else
                "reference runs disagree (flaky tests)",
        details={"runs": [list(s) for s in sets]}))

    coverage = _coverage(pos.out_dir / "coverage.json", reference, originals) if cov_files else None
    return {"negative": neg, "positive": pos, "feature_ids": feature_ids, "gates": gates,
            "feature_negative": f_neg, "feature_positive": p1, "regression": reg_pos,
            "coverage": coverage}


def _coverage(path: Path, reference: ReferenceSolution,
              originals: dict[str, str | None]) -> dict | None:
    """Share of the reference's added/changed executable lines executed by the feature tests."""
    if not path.exists():
        return None
    files = json.loads(path.read_text(encoding="utf-8")).get("files", {})
    total, covered, per_file = 0, 0, {}
    for ch in reference.changes:
        info = files.get(ch.path)
        if not info:
            continue
        executed = set(info.get("executed_lines", []))
        executable = executed | set(info.get("missing_lines", []))
        relevant = changed_lines(originals.get(ch.path), ch.content) & executable
        hit = relevant & executed
        total += len(relevant)
        covered += len(hit)
        per_file[ch.path] = {"statements": len(relevant), "covered": len(hit),
                             "missing_lines": sorted(relevant - executed),
                             "percent": round(100 * len(hit) / len(relevant), 1) if relevant
                             else None}
    return {"changed_statements": total, "covered": covered,
            "percent": round(100 * covered / total, 1) if total else None,
            "files": per_file, "tool": COVERAGE_PIN}


def run_mutation(
    ctx: ValidationContext,
    feature_tests: list[TestFile],
    reference: ReferenceSolution,
    original_contents: dict[str, str | None],
    semantic: list[tuple[str, dict[str, str]]],
    label: str,
) -> tuple[MutationResult, MutationResult]:
    """Run AST (diff-scoped) mutants and semantic mutants in one container."""
    tests = {t.path: t.content for t in feature_tests}
    overlay = {c.path: c.content for c in reference.changes}
    ast_mutants = []
    if ctx.adapter.supports_ast_mutation:
        per_file = max(5, ctx.max_mutants // max(1, len(reference.changes)))
        for ch in reference.changes:
            if language_of(ch.path) != "python" or is_test_path(ch.path):
                continue
            lines = changed_lines(original_contents.get(ch.path), ch.content)
            ast_mutants += generate_mutants(ch.path, ch.content, lines, per_file, ctx.seed)
        ast_mutants = ast_mutants[: ctx.max_mutants]
    overlays = [MutantOverlay(m.mutant_id, {m.file: m.content}) for m in ast_mutants]
    overlays += [MutantOverlay(f"s{i + 1}", files) for i, (_, files) in enumerate(semantic)]

    ast_result = MutationResult(engine="codeforge-ast (diff-scoped, mutmut-style operators)",
                                supported=ctx.adapter.supports_ast_mutation)
    sem_result = MutationResult(engine="llm-semantic-mutants")
    if not overlays:
        ast_result.note = "no mutable lines" if ctx.adapter.supports_ast_mutation else \
            f"AST mutation unsupported for {ctx.adapter.language}"
        sem_result.note = "no semantic mutants generated"
        return ast_result, sem_result

    plan = TestPlan(overlay=overlay, feature_tests=tests, mutants=overlays,
                    mutant_test_paths=list(tests))
    res = execute(plan, ctx.adapter, ctx.image, ctx.sandbox, ctx.out_dir / label / "mutation",
                  timeout=120 * len(overlays) + 300)

    def outcome(mid: str) -> tuple[bool, list[str], bool]:
        run = res.mutant_runs[mid]
        failing = run.failed + [e for e in run.errors if not e.startswith("<")]
        crashed = run.exit_code not in (0, None) and not run.passed and not failing
        killed = bool(failing) or crashed or run.timed_out
        errored = run.exit_code is None
        return killed, failing[:5], errored

    for m in ast_mutants:
        killed, by, errored = outcome(m.mutant_id)
        ast_result.outcomes.append(MutantOutcome(
            mutant_id=m.mutant_id, operator=m.operator, file=m.file, line=m.line,
            description=m.description, killed=killed, killed_by=by, diff=m.diff))
        ast_result.errors += int(errored)
    for i, (fault, files) in enumerate(semantic):
        mid = f"s{i + 1}"
        killed, by, errored = outcome(mid)
        path = next(iter(files))
        sem_result.outcomes.append(MutantOutcome(
            mutant_id=mid, operator="semantic", file=path, line=0, description=fault,
            killed=killed, killed_by=by, diff=_diff(overlay.get(path, ""), files[path], path)))
        sem_result.errors += int(errored)
    for r in (ast_result, sem_result):
        r.total = len(r.outcomes)
        r.killed = sum(o.killed for o in r.outcomes)
        r.survived = r.total - r.killed
        r.score = round(r.killed / r.total, 3) if r.total else None
    return ast_result, sem_result


def _diff(a: str, b: str, path: str) -> str:
    import difflib

    return "".join(difflib.unified_diff(a.splitlines(keepends=True), b.splitlines(keepends=True),
                                        fromfile=f"reference/{path}", tofile=f"mutant/{path}",
                                        n=1))
