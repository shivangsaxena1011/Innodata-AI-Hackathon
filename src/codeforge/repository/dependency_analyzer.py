"""Dependency manifest discovery, package manager, framework and test framework detection."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from codeforge.utils.fs import sha256_file

MANIFESTS = (
    "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "requirements-dev.txt",
    "requirements-test.txt", "dev-requirements.txt", "test-requirements.txt", "Pipfile",
    "Pipfile.lock", "poetry.lock", "uv.lock", "tox.ini", "pytest.ini", "package.json",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "go.mod", "go.sum", "Cargo.toml",
    "Cargo.lock", "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile", "composer.json",
)

PY_FRAMEWORKS = ("django", "flask", "fastapi", "starlette", "pandas", "sqlalchemy", "pydantic",
                 "click", "typer")
JS_FRAMEWORKS = ("next", "react", "vue", "express", "fastify", "koa", "@nestjs/core", "svelte")


@dataclass
class DependencyInfo:
    manifests: dict[str, str] = field(default_factory=dict)   # path -> sha256
    package_manager: str | None = None
    framework: str | None = None
    test_framework: str | None = None
    runtime_version: str | None = None
    python_requirements: list[str] = field(default_factory=list)  # requirement files to install
    installable_project: bool = False
    node_test_script: str | None = None


def _read(root: Path, rel: str) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def analyze_dependencies(root: Path, files: list[str], primary_language: str) -> DependencyInfo:
    info = DependencyInfo()
    top = {f for f in files if "/" not in f}
    for name in MANIFESTS:
        if name in top:
            info.manifests[name] = sha256_file(root / name)

    if primary_language == "python":
        _python(root, files, top, info)
    elif primary_language in ("javascript", "typescript"):
        _node(root, top, info)
    return info


def _python(root: Path, files: list[str], top: set[str], info: DependencyInfo) -> None:
    text_blob = ""
    if "pyproject.toml" in top:
        raw = _read(root, "pyproject.toml")
        text_blob += raw.lower()
        try:
            data = tomllib.loads(raw)
        except tomllib.TOMLDecodeError:
            data = {}
        rp = data.get("project", {}).get("requires-python")
        info.runtime_version = rp
        info.installable_project = "build-system" in data or "project" in data
        if "tool" in data and "poetry" in data["tool"]:
            info.package_manager = "poetry"
        elif "uv.lock" in top:
            info.package_manager = "uv"
    if "setup.py" in top or "setup.cfg" in top:
        info.installable_project = True
    info.python_requirements = sorted(
        f for f in top if re.fullmatch(r"(dev-|test-)?requirements([-_.][\w-]+)?\.txt", f)
    )
    for req in info.python_requirements:
        text_blob += _read(root, req).lower()
    info.package_manager = info.package_manager or "pip"

    for fw in PY_FRAMEWORKS:
        if re.search(rf"(^|[\"'\s\n]){re.escape(fw)}([\s<>=~!\[\"',;]|$)", text_blob, re.M):
            info.framework = fw
            break
    has_pytest_cfg = ("pytest.ini" in top or "[tool.pytest" in text_blob or "pytest" in text_blob
                      or any(f.endswith("conftest.py") for f in files))
    has_tests = any(re.search(r"(^|/)(test_[^/]*|[^/]*_test)\.py$", f) for f in files)
    if has_pytest_cfg or has_tests:
        info.test_framework = "pytest"


def _node(root: Path, top: set[str], info: DependencyInfo) -> None:
    info.package_manager = ("pnpm" if "pnpm-lock.yaml" in top else
                            "yarn" if "yarn.lock" in top else "npm")
    try:
        pkg = json.loads(_read(root, "package.json") or "{}")
    except json.JSONDecodeError:
        pkg = {}
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    info.framework = next((f for f in JS_FRAMEWORKS if f in deps), None)
    info.runtime_version = (pkg.get("engines") or {}).get("node")
    script = (pkg.get("scripts") or {}).get("test")
    info.node_test_script = script
    for fw in ("vitest", "jest", "mocha"):
        if fw in deps or (script and fw in script):
            info.test_framework = fw
            break
    else:
        if script and "node --test" in script:
            info.test_framework = "node:test"
