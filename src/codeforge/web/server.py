"""CodeForge AI web dashboard (FastAPI). Serves the static frontend and a small JSON API.

Every number the UI shows comes from real pipeline output on disk (reports/ and
generated_tasks/) or from live events of a running pipeline. Binds to localhost by default.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from codeforge import DEVELOPERS, TEAM_NAME, __version__
from codeforge.config import get_settings
from codeforge.logging_config import configure_logging
from codeforge.utils import fs

STATIC = Path(__file__).parent / "static"
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
URL_RE = re.compile(r"^https://[\w.\-]+/[\w.\-~/]+$")

configure_logging()
app = FastAPI(title="CodeForge AI", version=__version__)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_lock = threading.Lock()
_runs: dict[str, dict] = {}


class RunRequest(BaseModel):
    repo: str = "sample"
    ref: str | None = None
    tasks: int = Field(1, ge=1, le=5)
    harbor: bool = True
    model: str | None = None


class AnalyzeRequest(BaseModel):
    repo: str = "sample"
    ref: str | None = None


def _validate_repo(repo: str) -> str:
    repo = repo.strip()
    if repo == "sample" or URL_RE.match(repo):
        return repo
    path = Path(repo).expanduser()
    if path.is_dir() and (path / ".git").exists():
        return str(path.resolve())
    raise HTTPException(400, "repo must be 'sample', an https Git URL, or a local git repo path")


def _safe(part: str) -> str:
    if not SAFE_ID.match(part):
        raise HTTPException(400, "invalid identifier")
    return part


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """Serve the page with asset URLs stamped by modification time (cache busting)."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for asset in ("styles.css", "app.js"):
        stamp = int((STATIC / asset).stat().st_mtime)
        html = html.replace(f"/static/{asset}\"", f"/static/{asset}?v={stamp}\"")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/api/status")
def status() -> dict:
    from codeforge.ai.llm_client import provider_status
    from codeforge.environment.docker_builder import DockerSandbox
    from codeforge.harbor.harbor_validator import harbor_version

    running = [rid for rid, r in _runs.items() if r["status"] == "running"]
    return {"version": __version__, "team": TEAM_NAME, "developers": list(DEVELOPERS),
            "docker": DockerSandbox().version(), "harbor": harbor_version(),
            "llm": provider_status(), "running": running}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    from codeforge.pipeline import SAMPLE_DIR
    from codeforge.repository import git_manager
    from codeforge.repository.repository_profiler import profile_repository

    s = get_settings()
    source = _validate_repo(req.repo)
    if source == "sample":
        source = str(git_manager.materialize_sample(SAMPLE_DIR, s.workspace_dir / "samples" /
                                                    "shopcart"))
    try:
        co = git_manager.checkout(source, s.workspace_dir, req.ref, max_repo_mb=s.max_repo_mb)
        p = profile_repository(co, cache_dir=s.cache_dir)
    except Exception as exc:  # surfaced to the UI as a readable error
        raise HTTPException(400, f"{type(exc).__name__}: {exc}") from exc
    rm = p.repository_map
    return {
        "name": p.repository_name, "url": p.repository_url, "commit": p.starting_commit_sha,
        "branch": p.branch, "language": p.primary_language, "languages": p.detected_languages,
        "framework": p.framework, "test_framework": p.test_framework, "adapter": p.adapter,
        "supported": p.supported, "unsupported_reason": p.unsupported_reason,
        "package_manager": p.package_manager, "manifests": list(p.dependency_files),
        "test_dirs": p.test_dirs, "source_dirs": p.source_dirs,
        "files": len(rm.files) if rm else 0, "symbols": len(rm.symbols) if rm else 0,
        "test_files": sum(1 for f in rm.files if f.is_test) if rm else 0,
        "repo_map": rm.rendered if rm else "", "extension_points": rm.extension_points[:12]
        if rm else [], "top_symbols": [s.model_dump() for s in (rm.ranked_symbols[:12] if rm
                                                                 else [])],
        "important_files": p.important_files,
        "is_sample": req.repo == "sample",
    }


def _run_worker(run_id: str, req: RunRequest) -> None:
    from codeforge.ai.llm_client import LLMClient
    from codeforge.pipeline import Pipeline

    state = _runs[run_id]
    events_path = get_settings().reports_dir / run_id / "events.jsonl"

    def sink(event: dict) -> None:
        state["events"].append(event)
        events_path.parent.mkdir(parents=True, exist_ok=True)
        with open(events_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, default=str) + "\n")

    try:
        s = get_settings()
        pipeline = Pipeline(s, llm=LLMClient(s, model=req.model), on_event=sink)
        summary = pipeline.run(req.repo, req.ref, req.tasks, harbor=req.harbor, run_id=run_id)
        state["summary"] = summary
        state["status"] = summary.get("status", "failed")
    except Exception as exc:  # pragma: no cover - defensive
        state["status"] = "failed"
        state["error"] = str(exc)
    finally:
        _lock.release()


@app.post("/api/runs")
def start_run(req: RunRequest) -> dict:
    req.repo = _validate_repo(req.repo)
    if not _lock.acquire(blocking=False):
        raise HTTPException(409, "a run is already in progress (one at a time keeps Docker "
                                 "and the free model quota healthy)")
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    run_id = f"{stamp}-web-{uuid.uuid4().hex[:6]}"
    _runs[run_id] = {"run_id": run_id, "status": "running", "events": [], "request":
                     req.model_dump(), "started_at": datetime.now(UTC).isoformat()}
    threading.Thread(target=_run_worker, args=(run_id, req), daemon=True).start()
    return {"run_id": run_id}


@app.get("/api/runs")
def list_runs() -> list[dict]:
    from codeforge.reporting.evidence_manager import list_runs as disk_runs

    runs = disk_runs(get_settings().reports_dir)
    known = {r["run_id"] for r in runs}
    live = [{"run_id": rid, "status": r["status"], "started_at": r["started_at"]}
            for rid, r in _runs.items() if rid not in known]
    return live + runs


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, since: int = 0) -> dict:
    run_id = _safe(run_id)
    if run_id in _runs:
        r = _runs[run_id]
        return {"run_id": run_id, "status": r["status"], "events": r["events"][since:],
                "next": len(r["events"]), "summary": r.get("summary"), "error": r.get("error")}
    run_dir = get_settings().reports_dir / run_id
    if not (run_dir / "summary.json").exists():
        raise HTTPException(404, "run not found")
    events = []
    if (run_dir / "events.jsonl").exists():
        events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(
            encoding="utf-8").splitlines() if line.strip()]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    return {"run_id": run_id, "status": summary.get("status"), "events": events[since:],
            "next": len(events), "summary": summary}


@app.get("/api/runs/{run_id}/report", response_class=HTMLResponse)
def run_report(run_id: str) -> FileResponse:
    path = get_settings().reports_dir / _safe(run_id) / "report.html"
    if not path.exists():
        raise HTTPException(404, "report not found")
    return FileResponse(path)


def _task_dirs() -> list[Path]:
    out = get_settings().output_dir
    return sorted((p.parent for p in out.glob("*/*/task_manifest.json")
                   if not p.parent.parent.name.startswith("_")),
                  key=lambda p: p.stat().st_mtime, reverse=True)


@app.get("/api/tasks")
def list_tasks() -> list[dict]:
    tasks = []
    for d in _task_dirs():
        m = json.loads((d / "task_manifest.json").read_text(encoding="utf-8"))
        v = m.get("validation", {})
        tasks.append({
            "repo": d.parent.name, "task_id": d.name, "title": m.get("title"),
            "archetype": m.get("archetype"), "commit": m["repository"]["starting_commit_sha"],
            "language": m["repository"]["language"], "status": v.get("status"),
            "score": v.get("validity_score"), "mutation_score": v.get("mutation_score"),
            "semantic_mutant_score": v.get("semantic_mutant_score"),
            "gates": v.get("gates", []), "generated_at": m.get("generated_at"),
            "coverage": (v.get("coverage") or {}).get("percent"),
        })
    return tasks


def _task_dir(repo: str, task_id: str) -> Path:
    d = get_settings().output_dir / _safe(repo) / _safe(task_id)
    if not (d / "task_manifest.json").exists():
        raise HTTPException(404, "task not found")
    return d


@app.get("/api/tasks/{repo}/{task_id}")
def get_task(repo: str, task_id: str) -> JSONResponse:
    d = _task_dir(repo, task_id)
    manifest = json.loads((d / "task_manifest.json").read_text(encoding="utf-8"))
    feature = {str(p.relative_to(d / "tests" / "feature")).replace("\\", "/"):
               p.read_text(encoding="utf-8") for p in (d / "tests" / "feature").rglob("*")
               if p.is_file()}
    validation_file = d / "validation" / "validation.json"
    validation = json.loads(validation_file.read_text(encoding="utf-8")) \
        if validation_file.exists() else None
    return JSONResponse({
        "manifest": manifest,
        "instruction": (d / "instruction.md").read_text(encoding="utf-8"),
        "diff": (d / "solution" / "reference.patch").read_text(encoding="utf-8")
        if (d / "solution" / "reference.patch").exists() else "",
        "task_toml": (d / "task.toml").read_text(encoding="utf-8"),
        "feature_tests": feature, "validation": validation,
    })


@app.get("/api/tasks/{repo}/{task_id}/download")
def download_task(repo: str, task_id: str) -> FileResponse:
    d = _task_dir(repo, task_id)
    zip_path = get_settings().cache_dir / "downloads" / f"{task_id}.zip"
    fs.zip_dir(d, zip_path)
    return FileResponse(zip_path, filename=f"{task_id}.zip", media_type="application/zip")
