"""CodeForge pipeline orchestrator.

repository -> profile -> environment -> baseline -> discovery -> spec -> (tests || reference)
-> negative/positive/regression/stability -> repair loop -> mutation -> Harbor package
-> harbor lint + oracle + nop -> leakage check -> score -> evidence.
"""

from __future__ import annotations

import logging
import re
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from codeforge import __version__
from codeforge.adapters.languages.base import LanguageAdapter
from codeforge.ai.llm_client import ChatModel, LLMClient
from codeforge.ai.structured_output import StructuredOutputError
from codeforge.config import PROJECT_ROOT, Settings, get_settings
from codeforge.discovery.feature_discovery import discover_features, existing_public_names
from codeforge.discovery.novelty_checker import TaskFingerprint, diversity_report
from codeforge.environment.docker_builder import DockerSandbox
from codeforge.environment.environment_validator import check_image_for_shortcuts, run_baseline
from codeforge.environment.profile_builder import EnvironmentSpec, build_environment
from codeforge.generation.mutant_generator import generate_semantic_mutants
from codeforge.generation.patch_generator import Worktree
from codeforge.generation.reference_generator import ReferenceError_, generate_reference
from codeforge.generation.task_generator import generate_spec, render_instruction
from codeforge.generation.test_generator import generate_tests
from codeforge.harbor import harbor_validator, task_builder
from codeforge.reporting import evidence_manager as ev
from codeforge.repository import git_manager, profiles
from codeforge.repository.repository_profiler import profile_repository
from codeforge.schemas.repository import DirtyPolicy, RepositoryProfile
from codeforge.schemas.task import FeatureCandidate, GeneratedTask, TaskSpec, TestFile
from codeforge.schemas.validation import (
    GateName,
    GateResult,
    GateStatus,
    ValidationResult,
    ValidityStatus,
)
from codeforge.utils import fs
from codeforge.validation import engine, validity_scorer
from codeforge.validation.independence_checker import check_python_tests
from codeforge.validation.leakage_checker import check_package

log = logging.getLogger(__name__)

EventSink = Callable[[dict], None]


def is_sample(source: str | None) -> bool:
    if not source or source == "sample":
        return True
    try:
        return Path(source).resolve() == SAMPLE_DIR.resolve()
    except OSError:
        return False


def resolve_source(source: str | None, workspace: Path) -> str:
    """'sample' (or the bundled sample's folder path) becomes a git repository with a
    deterministic commit; anything else is returned unchanged."""
    if is_sample(source):
        return str(git_manager.materialize_sample(SAMPLE_DIR, workspace / "samples" /
                                                  "shopcart"))
    return str(source)
_FRAME_RE = re.compile(r"^([\w./\\-]+\.\w+):(\d+):", re.M)


def diagnose_failures(run, changed_files: set[str], test_files: list[str]) -> dict:
    """Blame failing feature tests on the tests or on the reference, from tracebacks.

    - last frame inside a file the reference changed            -> reference
    - non-assertion error whose last frame is in unchanged code or in the test file
      (setup misuse of the existing API, bad imports)           -> tests
    - assertion failures in the test body                       -> unclear (spec mismatch)
    """
    votes = {"reference": 0, "tests": 0, "unclear": 0}
    examples: list[str] = []
    test_names = {Path(t).name for t in test_files}
    for tid, text in run.failure_text.items():
        frames = [f.replace("\\", "/") for f, _ in _FRAME_RE.findall(text)]
        last = frames[-1] if frames else ""
        is_assert = "AssertionError" in text or "\nE       assert" in text or \
            text.lstrip().startswith("assert")
        if last and any(last.endswith(c) for c in changed_files):
            votes["reference"] += 1
        elif not is_assert and (not last or Path(last).name in test_names or
                                not any(last.endswith(c) for c in changed_files)):
            votes["tests"] += 1
        else:
            votes["unclear"] += 1
        if len(examples) < 3:
            first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
            examples.append(f"{tid.split('::')[-1]}: {first_line[:160]} (at {last or '?'})")
    total = sum(votes.values())
    verdict = "unclear"
    if total:
        top = max(votes, key=votes.get)
        if votes[top] / total >= 0.6:
            verdict = top
    return {"verdict": verdict, "votes": votes,
            "summary": f"{verdict} ({votes}); " + "; ".join(examples)}
SAMPLE_DIR = PROJECT_ROOT / "examples" / "sample_target_repository"
REQUIRED_GATES = (GateName.BASELINE, GateName.NEGATIVE_CONTROL, GateName.POSITIVE_CONTROL,
                  GateName.REGRESSION, GateName.STABILITY, GateName.INDEPENDENCE,
                  GateName.MUTATION, GateName.SEMANTIC_MUTANTS)
HARBOR_GATES = (GateName.HARBOR_LINT, GateName.HARBOR_ORACLE, GateName.HARBOR_NOP,
                GateName.LEAKAGE)


@dataclass
class RepoContext:
    run_id: str
    run_dir: Path
    checkout: git_manager.RepoCheckout
    profile: RepositoryProfile
    adapter: LanguageAdapter
    env: EnvironmentSpec
    validation_image: str
    regression_paths: list[str]
    shortcut_problems: list[str] = field(default_factory=list)


@dataclass
class TaskOutcome:
    candidate: FeatureCandidate
    task: GeneratedTask | None
    validation: ValidationResult
    task_dir: Path | None = None
    error: str | None = None


class Pipeline:
    def __init__(self, settings: Settings | None = None, llm: ChatModel | None = None,
                 on_event: EventSink | None = None):
        self.s = settings or get_settings()
        self.llm = llm or LLMClient(self.s)
        self.sandbox = DockerSandbox(self.s)
        self._sink = on_event

    # ------------------------------------------------------------------ events
    def emit(self, stage: str, status: str, message: str, **data: object) -> None:
        event = {"ts": datetime.now(UTC).isoformat(), "stage": stage, "status": status,
                 "message": message, "data": data}
        log.info("[%s] %s: %s", stage, status, message)
        if self._sink:
            try:
                self._sink(event)
            except Exception:  # pragma: no cover - UI sinks must never break a run
                log.exception("event sink failed")

    # ------------------------------------------------------------- repository
    def prepare(self, source: str | None, ref: str | None = None,
                dirty_policy: DirtyPolicy = DirtyPolicy.REFUSE,
                run_id: str | None = None) -> RepoContext:
        ws = self.s.workspace_dir
        if is_sample(source):
            self.emit("repository", "info", "using the bundled CodeForge sample repository "
                      "(shopcart). It is NOT the Innodata-supplied repository.")
        source = resolve_source(source, ws)
        self.emit("repository", "started", f"resolving {source} @ {ref or 'HEAD'}")
        co = git_manager.checkout(source, ws, ref, dirty_policy, self.s.max_repo_mb)
        self.emit("repository", "done", f"pinned commit {co.sha[:12]}", sha=co.sha,
                  branch=co.branch, url=co.url)

        self.emit("analysis", "started", "parsing with tree-sitter and ranking the repo map")
        profile = profile_repository(co, cache_dir=self.s.cache_dir)
        rm = profile.repository_map
        self.emit("analysis", "done",
                  f"{profile.primary_language} · {len(rm.files) if rm else 0} files · "
                  f"{len(rm.symbols) if rm else 0} symbols",
                  language=profile.primary_language, framework=profile.framework,
                  test_framework=profile.test_framework, adapter=profile.adapter)
        if not profile.supported:
            raise RuntimeError(profile.unsupported_reason or "unsupported repository")
        adapter = profiles.adapter_by_name(profile.adapter)
        assert adapter is not None

        run_id = run_id or ev.new_run_id(profile.repository_name)
        run_dir = self.s.reports_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        self.emit("environment", "started", "building the Docker environment")
        env = build_environment(profile, co.snapshot_dir, ws / "env" / profile.repository_name
                                / co.sha[:12], adapter, self.sandbox, run_dir / "environment")
        val_image = engine.build_validation_image(self.sandbox, env.image_tag,
                                                  ws / "env" / "validation" / co.sha[:12],
                                                  profile.primary_language)
        problems = check_image_for_shortcuts(env.image_tag, self.sandbox,
                                             run_dir / "environment" / "shortcut_check")
        self.emit("environment", "done", f"image {env.image_tag} (base {env.base_image})",
                  image=env.image_tag, base_image=env.base_image, shortcut_problems=problems)

        self.emit("baseline", "started", f"running the original test suite "
                  f"{self.s.baseline_runs}x")
        baseline = run_baseline(profile, adapter, env.image_tag, self.sandbox,
                                run_dir / "baseline", runs=self.s.baseline_runs)
        profile.baseline_test_status = baseline
        status = "done" if baseline.healthy else "failed"
        self.emit("baseline", status, f"{len(baseline.passed)} passing, {len(baseline.failed)} "
                  f"failing, {len(baseline.flaky)} flaky", passed=len(baseline.passed),
                  failed=len(baseline.failed), flaky=len(baseline.flaky), notes=baseline.notes)
        ev.write_json(run_dir / "repository_profile.json", profile)
        if not baseline.healthy:
            raise RuntimeError("baseline test suite is not healthy; see baseline evidence")
        return RepoContext(run_id, run_dir, co, profile, adapter, env, val_image,
                           adapter.regression_paths(profile), problems)

    # ---------------------------------------------------------------- tasks
    def _registry_path(self, profile: RepositoryProfile) -> Path:
        return self.s.output_dir / profile.repository_name / "registry.json"

    def _load_registry(self, profile: RepositoryProfile) -> list[TaskFingerprint]:
        path = self._registry_path(profile)
        if not path.exists():
            return []
        data = ev.read_json(path)
        return [TaskFingerprint.from_dict(d) for d in data.get("tasks", [])
                if d.get("commit") == profile.starting_commit_sha]

    def _save_registry(self, profile: RepositoryProfile, fp: TaskFingerprint, task_id: str
                       ) -> None:
        path = self._registry_path(profile)
        data = ev.read_json(path) if path.exists() else {"tasks": []}
        data["tasks"] = [d for d in data["tasks"] if d.get("task_id") != task_id]
        data["tasks"].append({**fp.to_dict(), "task_id": task_id,
                              "commit": profile.starting_commit_sha})
        ev.write_json(path, data)

    def run(self, source: str | None = None, ref: str | None = None, n_tasks: int = 1,
            dirty_policy: DirtyPolicy = DirtyPolicy.REFUSE, harbor: bool = True,
            run_id: str | None = None) -> dict:
        started = datetime.now(UTC).isoformat()
        summary: dict = {"codeforge_version": __version__, "started_at": started,
                         "status": "running", "tasks": [], "accepted": 0, "rejected": 0}
        ctx: RepoContext | None = None
        try:
            ctx = self.prepare(source, ref, dirty_policy, run_id)
            summary["run_id"] = ctx.run_id
            summary["repository"] = {"name": ctx.profile.repository_name,
                                     "url": ctx.profile.repository_url,
                                     "commit": ctx.profile.starting_commit_sha,
                                     "language": ctx.profile.primary_language,
                                     "framework": ctx.profile.framework,
                                     "test_framework": ctx.profile.test_framework}
            accepted = self._load_registry(ctx.profile)
            self.emit("discovery", "started", f"proposing {self.s.candidates_per_round} "
                      f"feature candidates")
            ranked, disc = discover_features(
                self.llm, ctx.profile, accepted, count=self.s.candidates_per_round,
                limit=n_tasks, novelty_threshold=self.s.novelty_threshold)
            ev.write_json(ctx.run_dir / "discovery.json", {
                "candidates": [{"candidate": r.candidate.model_dump(mode="json"),
                                "score": r.score, "accepted": r.accepted, "reason": r.reason}
                               for r in ranked],
                "llm": [{"model": r.model, "cached": r.cached} for r in disc.responses]})
            chosen = [r.candidate for r in ranked if r.accepted][:n_tasks]
            self.emit("discovery", "done", f"{len(chosen)} selected of {len(ranked)} proposed",
                      candidates=[{"title": r.candidate.title,
                                   "archetype": r.candidate.archetype.value,
                                   "accepted": r.accepted, "reason": r.reason,
                                   "novelty": r.candidate.novelty_score} for r in ranked])
            outcomes: list[TaskOutcome] = []
            for i, cand in enumerate(chosen, 1):
                self.emit("task", "started", f"[{i}/{len(chosen)}] {cand.title}",
                          task=cand.feature_id, archetype=cand.archetype.value)
                outcome = self.build_task(ctx, cand, harbor=harbor)
                outcomes.append(outcome)
                status = outcome.validation.final_validity_status.value
                self.emit("task", "done" if status == "valid" else "failed",
                          f"{cand.title}: {status}", task=cand.feature_id,
                          score=outcome.validation.score.total if outcome.validation.score
                          else None, reasons=outcome.validation.rejection_reasons)
                if status == "valid":
                    self._save_registry(ctx.profile, TaskFingerprint.of(cand), cand.feature_id)
                summary["tasks"].append(self._task_summary(outcome))
            valid = [o for o in outcomes if o.validation.final_validity_status ==
                     ValidityStatus.VALID]
            summary["accepted"] = len(valid)
            summary["rejected"] = len(outcomes) - len(valid)
            summary["variation"] = diversity_report([TaskFingerprint.of(o.candidate)
                                                     for o in valid])
            if len(valid) >= 2:
                from codeforge.reporting.variation import discrimination_matrix
                self.emit("variation", "started", "cross-task discrimination matrix")
                summary["discrimination_matrix"] = discrimination_matrix(
                    [o.task for o in valid if o.task], ctx, self.sandbox)
                self.emit("variation", "done", "matrix complete")
            summary["status"] = "completed"
        except Exception as exc:
            summary["status"] = "failed"
            summary["error"] = f"{type(exc).__name__}: {exc}"
            summary["traceback"] = traceback.format_exc()[-4000:]
            self.emit("run", "failed", summary["error"])
        finally:
            summary["finished_at"] = datetime.now(UTC).isoformat()
            summary["llm_usage"] = self.llm.usage.as_dict()
            if ctx:
                ev.write_json(ctx.run_dir / "summary.json", summary)
                from codeforge.reporting.html_report import write_html_report
                write_html_report(ctx.run_dir, summary)
        self.emit("run", summary["status"], f"{summary['accepted']} valid task(s), "
                  f"{summary['rejected']} rejected", run_id=summary.get("run_id"))
        return summary

    def _task_summary(self, o: TaskOutcome) -> dict:
        v = o.validation
        return {
            "task_id": o.candidate.feature_id, "title": o.candidate.title,
            "archetype": o.candidate.archetype.value, "status": v.final_validity_status.value,
            "score": v.score.total if v.score else None,
            "gates": [{"gate": g.gate.value, "status": g.status.value, "summary": g.summary}
                      for g in v.gates],
            "reasons": v.rejection_reasons, "task_dir": str(o.task_dir) if o.task_dir else None,
            "error": o.error,
        }

    # ----------------------------------------------------------- one task
    def build_task(self, ctx: RepoContext, cand: FeatureCandidate, harbor: bool = True
                   ) -> TaskOutcome:
        task_dir_ev = ctx.run_dir / cand.feature_id
        validation = ValidationResult(task_id=cand.feature_id)
        validation.gates.append(GateResult(
            gate=GateName.BASELINE, status=GateStatus.PASSED,
            summary=f"{len(ctx.profile.baseline_test_status.passed)} original tests pass "
                    f"consistently across {self.s.baseline_runs} runs",
            details=ctx.profile.baseline_test_status.model_dump()))
        root = ctx.checkout.snapshot_dir
        generation: dict = {"model": getattr(self.llm, "model", "unknown"), "attempts": [],
                            "seed": self.s.seed}
        try:
            self.emit("spec", "started", "writing requirements and acceptance criteria",
                      task=cand.feature_id)
            spec = generate_spec(self.llm, ctx.profile, root, cand).value
            self.emit("spec", "done", f"{len(spec.acceptance_criteria)} acceptance criteria",
                      task=cand.feature_id, spec=spec.model_dump(mode="json"))

            self.emit("tests", "started", "generating independent hidden tests (spec only)",
                      task=cand.feature_id)
            tests_res = generate_tests(self.llm, ctx.profile, root, spec, ctx.adapter)
            tests, trace = tests_res.value.files, tests_res.value.traceability
            self.emit("tests", "done", f"{len(trace)} traced tests in {tests[0].path}",
                      task=cand.feature_id)

            self.emit("reference", "started", "generating the reference implementation",
                      task=cand.feature_id)
            reference, ref_tree, ref_attempts = generate_reference(self.llm, ctx.profile, root,
                                                                   spec)
            generation["attempts"] += ref_attempts
            self.emit("reference", "done", f"{len(reference.changes)} file(s) changed",
                      task=cand.feature_id, diff=reference.unified_diff[:20000])

            originals = {c.path: ref_tree.original(c.path) for c in reference.changes}
            controls = None
            existing = existing_public_names(ctx.profile)
            for attempt in range(self.s.max_repair_attempts + 1):
                indep = self._independence(tests, spec, trace, existing, reference, ref_tree)
                self.emit("validation", "started", f"controls (attempt {attempt + 1})",
                          task=cand.feature_id)
                controls = engine.run_controls(self._vctx(ctx, task_dir_ev), tests, reference,
                                               originals, f"attempt-{attempt + 1}")
                gates = {g.gate: g for g in controls["gates"]}
                failing = [g for g in controls["gates"] if g.status == GateStatus.FAILED]
                record = {"attempt": attempt + 1, "gates": {g.gate.value: g.status.value
                                                            for g in controls["gates"]},
                          "independence_errors": indep.errors}
                validation.attempts.append(record)
                self.emit("validation", "done" if not failing and indep.ok else "failed",
                          ", ".join(f"{g.gate.value}={g.status.value}" for g in
                                    controls["gates"]), task=cand.feature_id,
                          gates=record["gates"])
                if not failing and indep.ok:
                    break
                if attempt == self.s.max_repair_attempts:
                    break
                # ---- repair loop: diagnose, regenerate only the failing component.
                neg, pos = gates[GateName.NEGATIVE_CONTROL], gates[GateName.POSITIVE_CONTROL]
                reg = gates[GateName.REGRESSION]
                log_tail = self._log_tail(controls["feature_positive"].log_path)
                blame = diagnose_failures(controls["feature_positive"],
                                          {c.path for c in reference.changes},
                                          [t.path for t in tests])
                validation.attempts[-1]["diagnosis"] = blame
                verdict = blame["verdict"] if pos.status == GateStatus.FAILED else "none"
                if reg.status == GateStatus.FAILED and verdict != "tests":
                    fix_reference = True          # the change broke existing behaviour
                elif indep.errors or neg.status == GateStatus.FAILED or verdict == "tests":
                    fix_reference = False         # the tests themselves are defective
                elif verdict == "reference":
                    fix_reference = True          # the new code crashes
                else:
                    fix_reference = attempt == 0  # spec mismatch: try reference, then tests
                if fix_reference:
                    note = self._reference_note(pos, reg, log_tail)
                    self.emit("repair", "started", "regenerating the reference implementation",
                              task=cand.feature_id, diagnosis=blame["summary"])
                    reference, ref_tree, more = generate_reference(
                        self.llm, ctx.profile, root, spec, repair_note=note)
                    generation["attempts"] += more
                    originals = {c.path: ref_tree.original(c.path) for c in reference.changes}
                else:
                    note = self._tests_note(neg, pos, indep, log_tail)
                    if blame["verdict"] == "tests":
                        note = (f"{note}\n\nDiagnosis: {blame['summary']}. The failures happen "
                                f"in test setup or existing code, before the new feature is "
                                f"exercised. Re-read the CURRENT source and the fixtures shown "
                                f"and construct objects exactly as the existing API requires.")
                    self.emit("repair", "started", "regenerating the hidden tests",
                              task=cand.feature_id, diagnosis=blame["summary"])
                    tests_res = generate_tests(self.llm, ctx.profile, root, spec, ctx.adapter,
                                               repair_note=note)
                    tests, trace = tests_res.value.files, tests_res.value.traceability

            assert controls is not None
            controls_ok = all(g.status != GateStatus.FAILED for g in controls["gates"]) and \
                indep.ok
            ast_res = sem_res = None
            if controls_ok:
                self.emit("mutation", "started", "diff-scoped AST mutants + semantic mutants",
                          task=cand.feature_id)
                semantic, skipped = generate_semantic_mutants(self.llm, spec, reference, ref_tree)
                ast_res, sem_res = engine.run_mutation(self._vctx(ctx, task_dir_ev), tests,
                                                       reference, originals, semantic, "final")
                sem_res.note = f"{len(skipped)} proposed mutant(s) could not be applied" \
                    if skipped else ""
                self.emit("mutation", "done",
                          f"AST {ast_res.killed}/{ast_res.total} killed · semantic "
                          f"{sem_res.killed}/{sem_res.total} killed", task=cand.feature_id,
                          ast_score=ast_res.score, semantic_score=sem_res.score)
                # ---- adversarial test strengthening: surviving mutants become new tests.
                for rnd in range(self.s.strengthen_rounds):
                    if ast_res.survived + sem_res.survived == 0:
                        break
                    better = self._strengthen(ctx, cand, spec, root, tests, reference,
                                              originals, semantic, ast_res, sem_res, existing,
                                              ref_tree, task_dir_ev, rnd + 1)
                    validation.attempts.append(better["record"])
                    if not better["adopted"]:
                        break
                    tests, trace, controls, indep = (better["tests"], better["trace"],
                                                     better["controls"], better["indep"])
                    ast_res, sem_res = better["ast"], better["sem"]

            validation.gates.extend(controls["gates"])
            validation.gates.append(self._independence_gate(indep))
            validation.feature_negative_control = controls["feature_negative"]
            validation.reference_positive_control = controls["feature_positive"]
            validation.regression_result = controls["regression"]
            validation.coverage_result = controls["coverage"]
            feature_ids = sorted(controls["feature_positive"].passed)
            if ast_res is not None and sem_res is not None:
                validation.mutation_result = ast_res
                validation.semantic_mutation_result = sem_res
                validation.gates += self._mutation_gates(ast_res, sem_res)

            task = GeneratedTask(
                task_id=cand.feature_id, title=spec.title, archetype=spec.archetype,
                starting_commit_sha=ctx.profile.starting_commit_sha,
                repository_url=ctx.profile.repository_url, spec=spec,
                instruction=render_instruction(spec, ctx.profile), reference=reference,
                feature_test_files=tests, feature_test_ids=feature_ids,
                regression_test_ids=sorted(set(ctx.profile.baseline_test_status.passed) -
                                           set(ctx.profile.baseline_test_status.flaky)),
                traceability=trace,
                generation_metadata={**generation, "llm_usage": self.llm.usage.as_dict()},
            )
            ac_cov = (sum(1 for v in indep.ac_coverage.values() if v) /
                      max(1, len(indep.ac_coverage)))
            self._finalize(validation, ac_cov, len(spec.acceptance_criteria), harbor_done=False)
            ev.write_json(task_dir_ev / "task.json", task)

            task_dir = None
            if validation.final_validity_status == ValidityStatus.VALID or not harbor:
                task_dir = self._package(ctx, task, validation, task_dir_ev, generation, harbor)
            ev.write_json(task_dir_ev / "validation.json", validation)
            return TaskOutcome(cand, task, validation, task_dir)
        except (StructuredOutputError, ReferenceError_, RuntimeError, ValueError) as exc:
            validation.final_validity_status = ValidityStatus.REJECTED
            validation.rejection_reasons.append(f"{type(exc).__name__}: {exc}")
            ev.write_json(task_dir_ev / "validation.json", validation)
            self.emit("task", "failed", f"generation failed: {exc}", task=cand.feature_id)
            return TaskOutcome(cand, None, validation, None, str(exc))

    def _strengthen(self, ctx: RepoContext, cand: FeatureCandidate, spec: TaskSpec, root: Path,
                    tests: list[TestFile], reference, originals: dict, semantic: list,
                    ast_res, sem_res, existing: set[str], ref_tree: Worktree, task_ev: Path,
                    rnd: int) -> dict:
        """Regenerate tests with surviving mutants as counter-examples. The new tests are
        adopted only if every control still passes and strictly more mutants are killed."""
        survivors = [o for o in sem_res.outcomes + ast_res.outcomes if not o.killed][:8]
        lines = []
        for o in survivors:
            lines.append(f"- {o.description} ({o.file}:{o.line})\n```diff\n{o.diff[:1500]}\n```")
        note = ("The current hidden tests (below) PASS against these WRONG implementations, so "
                "they are too weak. Keep every existing test that is correct, and ADD tests "
                "that fail on each wrong implementation while still passing on a correct "
                "implementation of the specification. Only test behaviour the specification "
                "states; if a mutant is behaviourally equivalent to the spec, ignore it.\n\n"
                + "\n".join(lines) + f"\n\nCurrent test file:\n```\n{tests[0].content}\n```")
        self.emit("strengthen", "started", f"round {rnd}: {len(survivors)} surviving mutants "
                  f"become counter-examples", task=cand.feature_id)
        record: dict = {"strengthen_round": rnd, "survivors": len(survivors), "adopted": False}
        try:
            res = generate_tests(self.llm, ctx.profile, root, spec, ctx.adapter, repair_note=note)
        except StructuredOutputError as exc:
            record["error"] = str(exc)
            return {"adopted": False, "record": record}
        new_tests, new_trace = res.value.files, res.value.traceability
        indep = self._independence(new_tests, spec, new_trace, existing, reference, ref_tree)
        controls = engine.run_controls(self._vctx(ctx, task_ev), new_tests, reference, originals,
                                       f"strengthen-{rnd}")
        record["gates"] = {g.gate.value: g.status.value for g in controls["gates"]}
        if any(g.status == GateStatus.FAILED for g in controls["gates"]) or not indep.ok:
            record["reason"] = "strengthened tests failed a control; kept the previous tests"
            self.emit("strengthen", "failed", record["reason"], task=cand.feature_id)
            return {"adopted": False, "record": record}
        ast2, sem2 = engine.run_mutation(self._vctx(ctx, task_ev), new_tests, reference,
                                         originals, semantic, f"strengthen-{rnd}")
        before, after = ast_res.killed + sem_res.killed, ast2.killed + sem2.killed
        record.update({"killed_before": before, "killed_after": after})
        if after <= before:
            record["reason"] = "no additional mutants killed; kept the previous tests"
            self.emit("strengthen", "done", record["reason"], task=cand.feature_id)
            return {"adopted": False, "record": record}
        record["adopted"] = True
        self.emit("strengthen", "done", f"adopted: mutants killed {before} → {after} (AST "
                  f"{ast2.killed}/{ast2.total}, semantic {sem2.killed}/{sem2.total})",
                  task=cand.feature_id, ast_score=ast2.score, semantic_score=sem2.score)
        return {"adopted": True, "record": record, "tests": new_tests, "trace": new_trace,
                "controls": controls, "indep": indep, "ast": ast2, "sem": sem2}

    # -------------------------------------------------------------- helpers
    def _vctx(self, ctx: RepoContext, task_ev: Path) -> engine.ValidationContext:
        return engine.ValidationContext(
            adapter=ctx.adapter, image=ctx.env.image_tag, validation_image=ctx.validation_image,
            sandbox=self.sandbox, baseline=ctx.profile.baseline_test_status,
            regression_paths=ctx.regression_paths, out_dir=task_ev,
            max_mutants=self.s.max_mutants, seed=self.s.seed)

    @staticmethod
    def _log_tail(path: str | None, n: int = 6000) -> str:
        if not path or not Path(path).exists():
            return ""
        return Path(path).read_text(encoding="utf-8", errors="replace")[-n:]

    @staticmethod
    def _reference_note(pos: GateResult, reg: GateResult, log_tail: str) -> str:
        parts = []
        if pos.status == GateStatus.FAILED:
            parts.append("The hidden acceptance tests FAILED against your implementation:\n"
                         f"failed={pos.details.get('failed')} errors={pos.details.get('errors')}")
        if reg.status == GateStatus.FAILED:
            parts.append(f"Your change BROKE existing tests: {reg.details.get('broken')}")
        parts.append(f"Test output (tail):\n{log_tail}")
        parts.append("Fix the implementation so it satisfies the specification exactly.")
        return "\n\n".join(parts)

    @staticmethod
    def _tests_note(neg: GateResult, pos: GateResult, indep, log_tail: str) -> str:
        parts = []
        if neg.status == GateStatus.FAILED:
            parts.append("These tests PASS on the original code, so they do not test the new "
                         f"feature: {neg.details.get('passing_on_original')}")
        if pos.status == GateStatus.FAILED:
            parts.append("These tests fail against a careful implementation of the spec; "
                         "re-derive expectations strictly from the specification: "
                         f"{pos.details.get('failed')} {pos.details.get('errors')}\n"
                         f"Test output (tail):\n{log_tail}")
        if indep.errors:
            parts.append("Static test-quality problems: " + "; ".join(indep.errors))
        return "\n\n".join(parts)

    def _independence(self, tests: list[TestFile], spec: TaskSpec, trace, existing: set[str],
                      reference, ref_tree: Worktree):
        from codeforge.validation.independence_checker import IndependenceReport
        if tests[0].path.endswith(".py"):
            import ast

            new_names: set[str] = set()
            for ch in reference.changes:
                try:
                    tree = ast.parse(ch.content)
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef | ast.ClassDef):
                        new_names.add(node.name)
            new_names -= existing
            return check_python_tests(tests[0].content, spec, trace, existing, new_names)
        return IndependenceReport(warnings=["static independence checks are Python-only"])

    @staticmethod
    def _independence_gate(indep) -> GateResult:
        status = GateStatus.FAILED if indep.errors else (
            GateStatus.WARNING if indep.warnings else GateStatus.PASSED)
        covered = sum(1 for v in indep.ac_coverage.values() if v)
        return GateResult(gate=GateName.INDEPENDENCE, status=status,
                          summary=f"{covered}/{len(indep.ac_coverage)} acceptance criteria "
                                  f"traced to tests; {len(indep.errors)} error(s), "
                                  f"{len(indep.warnings)} warning(s)",
                          details={"errors": indep.errors, "warnings": indep.warnings,
                                   "ac_coverage": indep.ac_coverage,
                                   "tests": indep.test_functions})

    def _mutation_gates(self, ast_res, sem_res) -> list[GateResult]:
        gates = []
        if not ast_res.supported:
            gates.append(GateResult(gate=GateName.MUTATION, status=GateStatus.UNSUPPORTED,
                                    summary=ast_res.note or "AST mutation unsupported"))
        elif ast_res.total == 0:
            gates.append(GateResult(gate=GateName.MUTATION, status=GateStatus.WARNING,
                                    summary="no mutable lines in the reference change"))
        else:
            ok = (ast_res.score or 0) >= self.s.min_mutation_score
            gates.append(GateResult(
                gate=GateName.MUTATION, status=GateStatus.PASSED if ok else GateStatus.FAILED,
                summary=f"mutation score {ast_res.score:.0%} ({ast_res.killed}/{ast_res.total} "
                        f"killed, threshold {self.s.min_mutation_score:.0%})",
                details={"survivors": [o.model_dump() for o in ast_res.outcomes
                                       if not o.killed][:10]}))
        if sem_res.total == 0:
            gates.append(GateResult(gate=GateName.SEMANTIC_MUTANTS, status=GateStatus.WARNING,
                                    summary="no semantic mutants could be applied"))
        else:
            ok = (sem_res.score or 0) >= 0.5
            gates.append(GateResult(
                gate=GateName.SEMANTIC_MUTANTS,
                status=GateStatus.PASSED if sem_res.survived == 0 else
                (GateStatus.WARNING if ok else GateStatus.FAILED),
                summary=f"{sem_res.killed}/{sem_res.total} plausible wrong implementations "
                        f"caught", details={"outcomes": [o.model_dump() for o in
                                                         sem_res.outcomes]}))
        return gates

    def _finalize(self, v: ValidationResult, ac_cov: float, n_ac: int, harbor_done: bool
                  ) -> None:
        v.score = validity_scorer.score(v, ac_cov, n_ac)
        required = list(REQUIRED_GATES) + (list(HARBOR_GATES) if harbor_done else [])
        reasons = []
        for name in required:
            g = v.gate(name)
            if g is None:
                if not reasons:
                    reasons.append(f"{name.value}: not run")
            elif g.status == GateStatus.FAILED:
                reasons.append(f"{name.value}: {g.summary}")
        v.rejection_reasons = reasons
        v.final_validity_status = ValidityStatus.VALID if not reasons else \
            ValidityStatus.REJECTED

    def _package(self, ctx: RepoContext, task: GeneratedTask, v: ValidationResult,
                 task_ev: Path, generation: dict, harbor: bool) -> Path:
        out_parent = self.s.output_dir / ctx.profile.repository_name
        out_parent.mkdir(parents=True, exist_ok=True)

        def summary() -> dict:
            return {"status": v.final_validity_status.value,
                    "validity_score": v.score.total if v.score else 0.0,
                    "gates": [{"gate": g.gate.value, "status": g.status.value,
                               "summary": g.summary} for g in v.gates],
                    "mutation_score": v.mutation_result.score if v.mutation_result else None,
                    "semantic_mutant_score": v.semantic_mutation_result.score
                    if v.semantic_mutation_result else None,
                    "coverage": v.coverage_result}

        self.emit("harbor", "started", "packaging the Harbor task", task=task.task_id)
        task_dir = task_builder.build_task(
            self.s.harbor_org, task, ctx.profile, ctx.adapter, ctx.env.env_dir,
            ctx.checkout.snapshot_dir, ctx.regression_paths, out_parent, summary(), generation)
        problems = check_package(task_dir, task) + ctx.shortcut_problems
        v.gates.append(GateResult(
            gate=GateName.LEAKAGE, status=GateStatus.FAILED if problems else GateStatus.PASSED,
            summary="no leakage or shortcut found" if not problems else "; ".join(problems[:5]),
            details={"problems": problems}))
        if harbor:
            lint = harbor_validator.lint(task_dir)
            v.gates.append(GateResult(
                gate=GateName.HARBOR_LINT, status=GateStatus.PASSED if lint.ok
                else GateStatus.FAILED,
                summary="harbor lint: no findings" if lint.ok else
                f"harbor lint: {len(lint.findings)} finding(s)",
                details={"findings": lint.findings, "output": lint.output[-2000:]}))
            self.emit("harbor", "info", f"lint {'ok' if lint.ok else 'failed'}; running oracle",
                      task=task.task_id)
            stamp = datetime.now(UTC).strftime("%H%M%S")
            jobs = ctx.run_dir / "harbor_jobs"
            oracle = harbor_validator.run_trial(task_dir, jobs, "oracle",
                                                f"{task.task_id[:40]}-oracle-{stamp}")
            v.gates.append(GateResult(
                gate=GateName.HARBOR_ORACLE,
                status=GateStatus.PASSED if oracle.reward == 1.0 else GateStatus.FAILED,
                summary=f"oracle reward {oracle.reward}" + (f" ({oracle.exception})"
                                                           if oracle.exception else ""),
                details=oracle.__dict__))
            self.emit("harbor", "info", f"oracle reward {oracle.reward}; running nop control",
                      task=task.task_id)
            nop = harbor_validator.run_trial(task_dir, jobs, "nop",
                                             f"{task.task_id[:40]}-nop-{stamp}")
            v.gates.append(GateResult(
                gate=GateName.HARBOR_NOP,
                status=GateStatus.PASSED if nop.reward == 0.0 else GateStatus.FAILED,
                summary=f"nop (no changes) reward {nop.reward}" + (f" ({nop.exception})"
                                                                  if nop.exception else ""),
                details=nop.__dict__))
            v.harbor_validation = {"lint": lint.__dict__, "oracle": oracle.__dict__,
                                   "nop": nop.__dict__,
                                   "harbor_version": harbor_validator.harbor_version()}
            self.emit("harbor", "done", f"oracle={oracle.reward} nop={nop.reward}",
                      task=task.task_id, oracle=oracle.reward, nop=nop.reward)
        n_ac = len(task.spec.acceptance_criteria)
        ac_cov = v.score.components[1].score if v.score else 0.0
        self._finalize(v, ac_cov, n_ac, harbor_done=harbor)
        ev.write_json(task_ev / "validation.json", v)
        # Rewrite metadata/evidence with the final verdict (does not change task behaviour).
        task_dir = task_builder.build_task(
            self.s.harbor_org, task, ctx.profile, ctx.adapter, ctx.env.env_dir,
            ctx.checkout.snapshot_dir, ctx.regression_paths, out_parent, summary(), generation,
            evidence_dir=self._evidence_bundle(task_ev, v))
        if v.final_validity_status != ValidityStatus.VALID:
            rejected = self.s.output_dir / "_rejected" / ctx.profile.repository_name
            rejected.mkdir(parents=True, exist_ok=True)
            target = rejected / task_dir.name
            fs.rmtree(target)
            task_dir.rename(target)
            task_dir = target
        fs.zip_dir(task_dir, ctx.run_dir / "packages" / f"{task.task_id}.zip")
        return task_dir

    @staticmethod
    def _evidence_bundle(task_ev: Path, v: ValidationResult) -> Path:
        bundle = task_ev / "_bundle"
        fs.rmtree(bundle)
        bundle.mkdir(parents=True)
        ev.write_json(bundle / "validation.json", v)
        for pattern in ("attempt-*/negative/*.log", "attempt-*/positive/*.log",
                        "attempt-*/positive/coverage.json", "final/mutation/mutant-*.log"):
            for f in task_ev.glob(pattern):
                rel = f.relative_to(task_ev)
                target = bundle / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(f.read_bytes())
        return bundle
