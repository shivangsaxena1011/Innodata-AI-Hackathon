"""Python adapter: pip-installable or requirements-based projects tested with pytest."""

from __future__ import annotations

import re

from codeforge.adapters.languages.base import LanguageAdapter
from codeforge.schemas.repository import RepositoryProfile

PYTEST_PIN = "pytest==8.3.5"
SUPPORTED_PYTHONS = ("3.13", "3.12", "3.11", "3.10")


def choose_python(requires: str | None) -> str:
    """Pick the newest supported CPython that satisfies a simple `requires-python` spec."""
    if not requires:
        return "3.12"
    for ver in SUPPORTED_PYTHONS:
        if _satisfies(ver, requires):
            return ver
    return "3.12"


def _satisfies(ver: str, spec: str) -> bool:
    v = tuple(int(x) for x in ver.split("."))
    for clause in spec.split(","):
        m = re.match(r"\s*(>=|<=|==|~=|>|<|!=)\s*(\d+(?:\.\d+)*)", clause)
        if not m:
            continue
        op, raw = m.groups()
        target = tuple(int(x) for x in raw.split("."))[:2]
        target = target + (0,) * (2 - len(target))
        checks = {">=": v >= target, "<=": v <= target, ">": v > target, "<": v < target,
                  "==": v[: len(target)] == target, "~=": v >= target, "!=": v != target}
        if not checks[op]:
            return False
    return True


class PythonAdapter(LanguageAdapter):
    name = "python-pytest"
    language = "python"
    supports_ast_mutation = True

    def base_image(self, profile: RepositoryProfile) -> str:
        return f"python:{choose_python(profile.runtime_version)}-slim"

    def dockerfile(self, profile: RepositoryProfile, base_image: str) -> str:
        reqs = [f for f in profile.dependency_files if re.fullmatch(
            r"(dev-|test-)?requirements([-_.][\w-]+)?\.txt", f)]
        installs = [f"pip install -r {r}" for r in sorted(reqs)]
        if profile.build_command:
            installs.append(" ".join(profile.build_command))
        installs.append(f'python -c "import pytest" 2>/dev/null || pip install {PYTEST_PIN}')
        run = " && \\\n    ".join(installs)
        return (
            f"FROM {base_image}\n\n"
            "ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \\\n"
            "    PYTHONUNBUFFERED=1\n\n"
            "WORKDIR /app\n"
            "COPY repo/ /app/\n\n"
            f"RUN {run}\n"
        )

    def test_shell(self, test_paths: list[str], junit_path: str) -> str:
        paths = " ".join(test_paths) if test_paths else ""
        return (f"python -m pytest -p no:cacheprovider -q -o addopts='' --junitxml={junit_path} "
                f"{paths}")

    def feature_test_path(self, profile: RepositoryProfile, slug: str) -> str:
        base = profile.test_dirs[0] if profile.test_dirs else "tests"
        safe = re.sub(r"[^a-z0-9_]", "_", slug.lower())
        return f"{base}/test_codeforge_{safe}.py"

    def test_style_hint(self, profile: RepositoryProfile) -> str:
        return ("Write pytest tests (plain `def test_...` functions with `assert`, use "
                "`pytest.raises` for errors). Import only from the public modules named in the "
                "interface contract and the existing package. The test file must be "
                "self-contained: build its own objects, do not rely on conftest fixtures.")
