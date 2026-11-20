"""task.toml and task_manifest.json generation.

Only fields present in the installed Harbor's task schema are written (verified against
`harbor task schema`, schema_version 1.4, Harbor 0.26.0). Custom CodeForge provenance goes
in the free-form [metadata] table, which the schema allows.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from codeforge import DEVELOPERS, TEAM_NAME, __version__
from codeforge.schemas.repository import RepositoryProfile
from codeforge.schemas.task import GeneratedTask

SCHEMA_VERSION = "1.4"


def _toml_value(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int | float):
        return repr(float(v)) if isinstance(v, float) else str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {_toml_value(x)}" for k, x in v.items()) + " }"
    raise TypeError(f"unsupported TOML value: {type(v)}")


def _table(name: str, values: dict) -> list[str]:
    lines = [f"[{name}]"]
    lines += [f"{k} = {_toml_value(v)}" for k, v in values.items() if v is not None]
    return lines + [""]


def task_name(org: str, task: GeneratedTask) -> str:
    return f"{org}/{task.task_id}"


def build_task_toml(org: str, task: GeneratedTask, profile: RepositoryProfile,
                    validation_summary: dict) -> str:
    spec = task.spec
    est = float(spec.estimated_minutes or 30)
    lines = [
        f"schema_version = {_toml_value(SCHEMA_VERSION)}",
        f"source = {_toml_value(f'codeforge-ai {__version__}')}",
        "artifacts = " + _toml_value([{"source": "/app",
                                        "exclude": ["__pycache__", ".pytest_cache", "*.pyc",
                                                    "*.egg-info"]}]),
        "",
    ]
    lines += _table("task", {
        "name": task_name(org, task),
        "version": "1.0.0",
        "description": spec.summary[:500],
        "authors": [{"name": f"Team {TEAM_NAME}: {', '.join(DEVELOPERS)}"}],
        "keywords": ["codeforge", "feature-development", spec.archetype.value,
                     profile.primary_language],
    })
    lines += _table("metadata", {
        "author_name": f"Team {TEAM_NAME}",
        "author_email": "unknown",
        "difficulty": spec.difficulty.value,
        "category": "software_engineering",
        "tags": ["feature-development", spec.archetype.value, profile.primary_language],
        "expert_time_estimate_min": est,
        "junior_time_estimate_min": est * 2,
        "repository_name": profile.repository_name,
        "repository_url": profile.repository_url,
        "starting_commit_sha": profile.starting_commit_sha,
        "language": profile.primary_language,
        "test_framework": profile.test_framework or "unknown",
        "archetype": spec.archetype.value,
        "codeforge_version": __version__,
        "validity_score": float(validation_summary.get("validity_score", 0.0)),
        "validation_status": validation_summary.get("status", "unknown"),
    })
    lines += _table("verifier", {"timeout_sec": 1800.0, "environment_mode": "separate",
                                 "network_mode": "no-network"})
    lines += _table("agent", {"timeout_sec": 3600.0})
    lines += _table("environment", {"network_mode": "public", "build_timeout_sec": 900.0,
                                    "os": "linux", "cpus": 2, "memory_mb": 4096})
    return "\n".join(lines)


def build_manifest(task: GeneratedTask, profile: RepositoryProfile, env_base_image: str,
                   validation_summary: dict, generation: dict) -> dict:
    return {
        "codeforge_version": __version__,
        "team": {"name": TEAM_NAME, "developers": list(DEVELOPERS)},
        "generated_at": datetime.now(UTC).isoformat(),
        "task_id": task.task_id,
        "title": task.title,
        "archetype": task.archetype.value,
        "repository": {
            "name": profile.repository_name,
            "url": profile.repository_url,
            "starting_commit_sha": profile.starting_commit_sha,
            "branch_at_generation": profile.branch,
            "language": profile.primary_language,
            "framework": profile.framework,
            "runtime_version": profile.runtime_version,
            "test_framework": profile.test_framework,
            "dependency_manifest_sha256": profile.dependency_files,
            "baseline": profile.baseline_test_status.model_dump()
            if profile.baseline_test_status else None,
        },
        "environment": {"base_image": env_base_image},
        "tests": {"feature": task.feature_test_ids, "regression": task.regression_test_ids,
                  "files": [t.path for t in task.feature_test_files]},
        "traceability": [t.model_dump() for t in task.traceability],
        "reference": {"files": [c.path for c in task.reference.changes],
                      "explanation": task.reference.explanation},
        "validation": validation_summary,
        "generation": generation,
    }
