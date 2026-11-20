"""CodeForge AI command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from codeforge import DEVELOPERS, TEAM_NAME, __version__
from codeforge.config import get_settings
from codeforge.logging_config import configure_logging
from codeforge.schemas.repository import DirtyPolicy

app = typer.Typer(add_completion=False, help="CodeForge AI: a coding task factory for "
                  "evaluating AI coding systems. Build. Test. Benchmark.")


@app.callback()
def _main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    configure_logging("DEBUG" if verbose else "INFO")


@app.command()
def doctor() -> None:
    """Check Docker, Harbor and the (free) model provider configuration."""
    from codeforge.ai.llm_client import provider_status
    from codeforge.environment.docker_builder import DockerSandbox
    from codeforge.harbor.harbor_validator import harbor_version

    status = {
        "codeforge": __version__, "team": TEAM_NAME, "developers": list(DEVELOPERS),
        "docker": DockerSandbox().version(), "harbor": harbor_version(),
        "llm": provider_status(),
    }
    typer.echo(json.dumps(status, indent=2))
    if not status["docker"]:
        raise typer.Exit(1)


@app.command()
def analyze(
    repo: str = typer.Argument("sample", help="Git URL, local repo path, or 'sample'"),
    ref: str | None = typer.Option(None, help="branch, tag or commit"),
    dirty: DirtyPolicy = typer.Option(DirtyPolicy.REFUSE, help="policy for uncommitted changes"),
    budget: int = typer.Option(2500, help="token budget for the rendered repo map"),
) -> None:
    """Profile a repository and print its ranked map (no Docker or LLM needed)."""
    from codeforge.pipeline import SAMPLE_DIR
    from codeforge.repository import git_manager
    from codeforge.repository.repository_profiler import profile_repository

    s = get_settings()
    source = repo
    if repo == "sample":
        source = str(git_manager.materialize_sample(SAMPLE_DIR, s.workspace_dir / "samples" /
                                                    "shopcart"))
    co = git_manager.checkout(source, s.workspace_dir, ref, dirty, s.max_repo_mb)
    p = profile_repository(co, cache_dir=s.cache_dir, token_budget=budget)
    rm = p.repository_map
    typer.echo(f"repository  {p.repository_name}  {p.repository_url}")
    typer.echo(f"commit      {p.starting_commit_sha}  (branch {p.branch})")
    typer.echo(f"language    {p.primary_language}  {p.detected_languages}")
    typer.echo(f"framework   {p.framework}   tests: {p.test_framework}   adapter: {p.adapter}")
    typer.echo(f"manifests   {list(p.dependency_files)}")
    typer.echo(f"test dirs   {p.test_dirs}   source dirs: {p.source_dirs}")
    typer.echo("\n--- ranked repository map ---")
    typer.echo(rm.rendered if rm else "(none)")
    typer.echo("\n--- extension points ---")
    for point in (rm.extension_points if rm else [])[:12]:
        typer.echo(f"  {point}")


@app.command()
def run(
    repo: str = typer.Argument("sample", help="Git URL, local repo path, or 'sample'"),
    ref: str | None = typer.Option(None, help="branch, tag or commit"),
    tasks: int = typer.Option(1, "--tasks", "-n", min=1, max=10),
    dirty: DirtyPolicy = typer.Option(DirtyPolicy.REFUSE),
    harbor: bool = typer.Option(True, help="package and verify with Harbor (lint/oracle/nop)"),
    model: str | None = typer.Option(None, help="LiteLLM model id, e.g. gemini/gemini-2.5-flash"),
) -> None:
    """Generate and validate feature-development tasks end to end."""
    from codeforge.ai.llm_client import LLMClient
    from codeforge.pipeline import Pipeline

    s = get_settings()
    pipeline = Pipeline(s, llm=LLMClient(s, model=model))
    summary = pipeline.run(repo, ref, tasks, dirty, harbor)
    typer.echo("")
    for t in summary.get("tasks", []):
        typer.echo(f"{t['status'].upper():9} {t.get('score')!s:>5}  {t['title']}")
        for r in t.get("reasons", []):
            typer.echo(f"          - {r}")
        if t.get("task_dir"):
            typer.echo(f"          package: {t['task_dir']}")
    if summary.get("run_id"):
        typer.echo(f"\nreport: {s.reports_dir / summary['run_id'] / 'report.html'}")
    if summary["status"] != "completed":
        typer.echo(f"run failed: {summary.get('error')}")
        raise typer.Exit(1)


@app.command()
def evaluate(
    task_dir: Path = typer.Argument(..., exists=True, file_okay=False),
    agent: str = typer.Option("gemini-cli", help="Harbor agent name (see `harbor agent list`)"),
    model: str | None = typer.Option("gemini/gemini-2.5-flash"),
    attempts: int = typer.Option(1, min=1, max=5),
) -> None:
    """Benchmark a real AI coding agent on one validated task through Harbor."""
    from codeforge.evaluation.agent_runner import evaluate_agent

    result = evaluate_agent(task_dir, agent, model, attempts)
    typer.echo(json.dumps(result, indent=2))


@app.command()
def benchmark(
    agent: str = typer.Option("gemini-cli", help="Harbor agent (gemini-cli works with a free "
                                                 "GEMINI_API_KEY; nop = no-change control)"),
    models: str = typer.Option(
        "gemini/gemini-2.5-flash,gemini/gemini-3.5-flash,gemini/gemini-3.6-flash,"
        "gemini/gemini-3.7-flash",
        help="comma-separated models, rotated across tasks to spread free daily quotas"),
    repo: str | None = typer.Option(None, help="only tasks for this repository name"),
    attempts: int = typer.Option(1, min=1, max=5),
) -> None:
    """Run a real AI coding agent on every validated task and write a benchmark report."""
    from datetime import UTC, datetime

    from codeforge.evaluation.agent_runner import benchmark as run_benchmark

    s = get_settings()
    tasks = sorted(p.parent for p in s.output_dir.glob("*/*/task_manifest.json")
                   if not p.parent.parent.name.startswith("_") and
                   (repo is None or p.parent.parent.name == repo))
    if not tasks:
        typer.echo("no validated tasks found")
        raise typer.Exit(1)
    model_list = [m.strip() for m in models.split(",") if m.strip()] if agent != "nop" else []
    out = s.reports_dir / f"benchmark-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{agent}"
    summary = run_benchmark(tasks, agent, model_list or [None], attempts, out)
    typer.echo((out / "benchmark.md").read_text(encoding="utf-8"))
    typer.echo(f"report: {out / 'benchmark.json'}")
    if summary["pass_rate"] is None and summary["trials"]:
        typer.echo("no trial was graded (see quota_errors / errors)")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the CodeForge web dashboard."""
    import uvicorn

    typer.echo(f"CodeForge AI dashboard: http://{host}:{port}")
    uvicorn.run("codeforge.web.server:app", host=host, port=port, log_level="info")


@app.command()
def version() -> None:
    typer.echo(f"CodeForge AI {__version__} — Team {TEAM_NAME}: {', '.join(DEVELOPERS)}")


if __name__ == "__main__":
    app()
