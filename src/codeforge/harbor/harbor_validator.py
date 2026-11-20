"""Validate packages with the real Harbor CLI: `harbor lint`, then oracle and nop trials.

Nothing here simulates Harbor. Results are read from Harbor's own job output
(jobs/<job>/<trial>/result.json -> verifier_result.rewards).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from codeforge.config import Settings, get_settings
from codeforge.utils.proc import run

log = logging.getLogger(__name__)


def harbor_executable(settings: Settings | None = None) -> str | None:
    s = settings or get_settings()
    if s.harbor_bin:
        return s.harbor_bin
    found = shutil.which("harbor")
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / ("harbor.exe" if os.name == "nt" else "harbor")
    return str(candidate) if candidate.exists() else None


def harbor_version(settings: Settings | None = None) -> str | None:
    exe = harbor_executable(settings)
    if not exe:
        return None
    r = run([exe, "--version"], timeout=60)
    return r.stdout.strip() if r.ok else None


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["HARBOR_TELEMETRY"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    env["NO_COLOR"] = "1"
    return env


@dataclass
class LintResult:
    ok: bool
    findings: list[dict] = field(default_factory=list)
    output: str = ""


@dataclass
class TrialOutcome:
    agent: str
    ok: bool
    reward: float | None
    rewards: dict = field(default_factory=dict)
    exception: str | None = None
    job_dir: str = ""
    duration_sec: float = 0.0
    output_tail: str = ""


def lint(task_dir: Path, settings: Settings | None = None) -> LintResult:
    exe = harbor_executable(settings)
    if not exe:
        return LintResult(False, [], "harbor CLI not installed")
    r = run([exe, "lint", str(task_dir), "--json"], timeout=300, env=_env())
    try:
        findings = json.loads(r.stdout[r.stdout.find("["):] or "[]")
    except json.JSONDecodeError:
        findings = []
    return LintResult(r.ok and not findings, findings, r.output[-4000:])


def short_job(agent: str, task_dir: Path) -> str:
    """Short, unique job name. Harbor nests the agent's whole /app under the job directory,
    so long names overflow Windows' 260-character path limit."""
    import hashlib
    import time

    digest = hashlib.sha1(f"{task_dir}{time.time_ns()}".encode()).hexdigest()[:8]
    return f"{agent[:10]}-{digest}"


def run_trial(task_dir: Path, jobs_dir: Path | None, agent: str, job_name: str | None = None,
              model: str | None = None, timeout: int = 3600,
              settings: Settings | None = None, extra: list[str] | None = None) -> TrialOutcome:
    """Run one Harbor trial. Jobs always live under the short `<workspace>/hj` root (see
    `short_job`); `jobs_dir` is accepted for API compatibility but not used for output."""
    s = settings or get_settings()
    exe = harbor_executable(s)
    if not exe:
        return TrialOutcome(agent, False, None, exception="harbor CLI not installed")
    jobs_dir = s.workspace_dir / "hj"
    job_name = short_job(agent, task_dir)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    args = [exe, "run", "-p", str(task_dir), "-a", agent, "-e", "docker",
            "-o", str(jobs_dir), "--job-name", job_name, "-n", "1"]
    if model:
        args += ["-m", model]
    args += extra or []
    r = run(args, timeout=timeout, env=_env())
    job_dir = jobs_dir / job_name
    outcome = TrialOutcome(agent, False, None, job_dir=str(job_dir),
                           duration_sec=round(r.duration_sec, 1), output_tail=r.output[-3000:])
    results = sorted(p for p in job_dir.glob("*/result.json"))
    if not results:
        outcome.exception = "no trial result.json produced" + (" (timed out)" if r.timed_out
                                                               else "")
        return outcome
    data = json.loads(results[0].read_text(encoding="utf-8"))
    vr = data.get("verifier_result") or {}
    outcome.rewards = vr.get("rewards") or {}
    outcome.reward = outcome.rewards.get("reward")
    exc = data.get("exception_info")
    if exc:
        outcome.exception = (exc.get("exception_type", "") + ": " +
                             str(exc.get("exception_message", ""))[:500]).strip(": ")
    outcome.ok = outcome.reward is not None
    return outcome


def cleanup_images(task_name: str) -> None:
    """Best-effort removal of Harbor-built images for a task (keeps disk usage bounded)."""
    r = run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"], timeout=60)
    slug = task_name.split("/")[-1]
    for image in r.stdout.split():
        if slug in image and image.startswith("hb"):
            run(["docker", "rmi", "-f", image], timeout=120)
