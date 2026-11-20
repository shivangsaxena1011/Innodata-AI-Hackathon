"""Evidence storage: every run gets a directory with machine-readable records of what was
executed and what happened. Reports and the dashboard read only from here."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel


def new_run_id(repo_name: str) -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{repo_name[:24]}"


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, BaseModel):
        text = data.model_dump_json(indent=2)
    else:
        text = json.dumps(data, indent=2, default=_default)
    path.write_text(text, encoding="utf-8")
    return path


def _default(o: object) -> object:
    if isinstance(o, BaseModel):
        return o.model_dump(mode="json")
    if isinstance(o, Path):
        return o.as_posix()
    if isinstance(o, set | frozenset):
        return sorted(o)
    return str(o)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def list_runs(reports_dir: Path) -> list[dict]:
    runs = []
    for summary in sorted(reports_dir.glob("*/summary.json"), reverse=True):
        try:
            data = read_json(summary)
        except (OSError, json.JSONDecodeError):
            continue
        runs.append({"run_id": summary.parent.name, **{k: data.get(k) for k in (
            "repository", "started_at", "finished_at", "status", "accepted", "rejected")}})
    return runs
