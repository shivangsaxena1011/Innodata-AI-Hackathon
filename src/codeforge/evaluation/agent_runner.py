"""Benchmark real AI coding agents on validated tasks through Harbor's agent interface.

Oracle validation (does the task work?) and agent performance (can an AI solve it?) are kept
strictly separate. An agent counts as solving a task only when Harbor's verifier recorded
reward 1.0 for that trial. Trials that end in an infrastructure or quota error are reported
as errors, never as failures of the agent and never as successes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from codeforge.harbor.harbor_validator import TrialOutcome, run_trial

QUOTA_MARKERS = ("429", "quota", "resource_exhausted", "rate limit", "ratelimit")


def classify(outcome: TrialOutcome) -> str:
    """solved | unsolved | quota_error | error."""
    text = f"{outcome.exception or ''} {outcome.output_tail or ''}".lower()
    if outcome.reward == 1.0:
        return "solved"
    if any(m in text for m in QUOTA_MARKERS):
        return "quota_error"
    if outcome.reward is None:
        return "error"
    return "unsolved"


def evaluate_agent(task_dir: Path, agent: str, model: str | None, attempts: int = 1,
                   jobs: Path | None = None) -> dict:
    jobs = jobs or task_dir.parent.parent / "_agent_runs"
    manifest_path = task_dir / "task_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) \
        if manifest_path.exists() else {}
    trials = []
    for k in range(attempts):
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        outcome = run_trial(task_dir, jobs, agent, f"{task_dir.name[:40]}-{agent}-{stamp}-{k}",
                            model=model, timeout=5400)
        trials.append({
            "attempt": k + 1, "model": model, "outcome": classify(outcome),
            "reward": outcome.reward, "rewards": outcome.rewards,
            "exception": outcome.exception, "duration_sec": outcome.duration_sec,
            "agent_seconds": outcome.agent_seconds,
            "input_tokens": outcome.input_tokens, "output_tokens": outcome.output_tokens,
            "cost_usd": outcome.cost_usd, "model_info": outcome.model_info,
            "verifier": outcome.grading, "job_dir": outcome.job_dir,
        })
    solved = sum(t["outcome"] == "solved" for t in trials)
    valid_trials = sum(t["outcome"] in ("solved", "unsolved") for t in trials)
    return {
        "task_id": manifest.get("task_id", task_dir.name),
        "title": manifest.get("title"),
        "archetype": manifest.get("archetype"),
        "starting_commit_sha": (manifest.get("repository") or {}).get("starting_commit_sha"),
        "agent": agent, "model": model, "attempts": attempts, "solved": solved,
        "valid_trials": valid_trials,
        "pass_rate": round(solved / valid_trials, 3) if valid_trials else None,
        "trials": trials,
    }


def benchmark(task_dirs: list[Path], agent: str, models: list[str | None], attempts: int,
              out_dir: Path) -> dict:
    """Run `agent` on every task. Models rotate across tasks so free-tier daily quotas are
    spread out; each result records exactly which model was used."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, task_dir in enumerate(task_dirs):
        model = models[i % len(models)] if models else None
        results.append(evaluate_agent(task_dir, agent, model, attempts, jobs=out_dir / "jobs"))
        _write(out_dir, agent, results)  # keep partial results if a later task fails
    return _write(out_dir, agent, results)


def _write(out_dir: Path, agent: str, results: list[dict]) -> dict:
    trials = [t for r in results for t in r["trials"]]
    counted = [t for t in trials if t["outcome"] in ("solved", "unsolved")]
    summary = {
        "generated_at": datetime.now(UTC).isoformat(), "agent": agent,
        "tasks": len(results), "trials": len(trials),
        "solved": sum(t["outcome"] == "solved" for t in trials),
        "unsolved": sum(t["outcome"] == "unsolved" for t in trials),
        "quota_errors": sum(t["outcome"] == "quota_error" for t in trials),
        "errors": sum(t["outcome"] == "error" for t in trials),
        "pass_rate": round(sum(t["outcome"] == "solved" for t in counted) / len(counted), 3)
        if counted else None,
        "note": "pass_rate counts only trials the verifier graded; quota and infrastructure "
                "errors are listed separately. Oracle validation is in each task_manifest.json.",
        "results": results,
    }
    (out_dir / "benchmark.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "benchmark.md").write_text(_markdown(summary), encoding="utf-8")
    return summary


def _markdown(s: dict) -> str:
    rate = "n/a" if s["pass_rate"] is None else f"{s['pass_rate']:.0%}"
    lines = [f"# Agent benchmark: `{s['agent']}`", "",
             f"Generated {s['generated_at']}. Graded pass rate: **{rate}** "
             f"({s['solved']} solved, {s['unsolved']} unsolved, {s['quota_errors']} quota "
             f"errors, {s['errors']} other errors).", "",
             "| Task | Archetype | Model | Outcome | Reward | Feature pass | Regression pass "
             "| Tokens in/out | Agent time (s) | Total time (s) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in s["results"]:
        for t in r["trials"]:
            rw = t.get("rewards") or {}

            def fmt(v):
                return "—" if v is None else v
            tokens = "—" if t.get("input_tokens") is None else \
                f"{t['input_tokens']}/{t.get('output_tokens')}"
            lines.append(f"| {r['title']} | {r['archetype']} | `{t['model']}` | {t['outcome']} | "
                         f"{fmt(t['reward'])} | {fmt(rw.get('feature_pass_rate'))} | "
                         f"{fmt(rw.get('regression_pass_rate'))} | {tokens} | "
                         f"{fmt(t.get('agent_seconds'))} | {t['duration_sec']} |")
    errors = [(r["title"], t) for r in s["results"] for t in r["trials"]
              if t["outcome"] in ("quota_error", "error")]
    if errors:
        lines += ["", "## Errors (not counted as agent failures)", ""]
        lines += [f"- **{title}** ({t['outcome']}): {str(t.get('exception'))[:300]}"
                  for title, t in errors]
    lines += ["", s["note"], ""]
    return "\n".join(lines)
