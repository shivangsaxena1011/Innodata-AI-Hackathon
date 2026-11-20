"""tests/: verifier image, hidden feature tests, pristine regression tests, grader, test.sh.

The verifier runs in a SEPARATE container built from tests/Dockerfile (fresh dependencies,
nothing the agent installed or modified). Harbor re-materialises the agent's /app there as
an artifact. test.sh then:
  1. writes a zero reward first, so every execution path leaves a reward file;
  2. restores pristine original tests and test configuration (agents cannot weaken them);
  3. deletes any conftest.py / sitecustomize.py the agent created (pytest hook shortcuts);
  4. installs the hidden feature tests and runs feature + regression suites with JUnit;
  5. grades against expected.json with a stdlib-only grader.
"""

from __future__ import annotations

import json
import shlex
import shutil
from importlib import resources
from pathlib import Path

from codeforge.adapters.languages.base import LanguageAdapter
from codeforge.repository.language_detector import is_test_path
from codeforge.schemas.repository import RepositoryProfile
from codeforge.schemas.task import GeneratedTask
from codeforge.utils import fs
from codeforge.utils.fs import iter_repo_files

PRISTINE_CONFIG = ("conftest.py", "pytest.ini", "tox.ini", "setup.cfg")


def pristine_test_files(snapshot: Path) -> dict[str, str]:
    files = {}
    for rel in iter_repo_files(snapshot):
        name = rel.rsplit("/", 1)[-1]
        if is_test_path(rel) or name in PRISTINE_CONFIG:
            try:
                files[rel] = (snapshot / rel).read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
    return files


def build_test_sh(adapter: LanguageAdapter, feature_paths: list[str], regression_paths: list[str],
                  pristine_conftests: list[str]) -> str:
    q = shlex.quote
    feature_cmd = adapter.test_shell(feature_paths, "/logs/verifier/feature.xml")
    regression_cmd = adapter.test_shell(regression_paths, "/logs/verifier/regression.xml")
    keep = " ".join(q("./" + p) for p in pristine_conftests)
    return f"""#!/bin/bash
# CodeForge verifier. Hidden tests live only here; the agent never sees them.
set -uo pipefail
mkdir -p /logs/verifier
echo '{{"reward": 0.0}}' > /logs/verifier/reward.json
cd /app || {{ echo "missing /app"; exit 0; }}

# Remove agent-created pytest/interpreter hooks that could fake results.
KEEP=({keep})
while IFS= read -r f; do
  keep=0; for k in "${{KEEP[@]:-}}"; do [ "$f" = "$k" ] && keep=1; done
  [ "$keep" = 0 ] && echo "removing unexpected $f" && rm -f "$f"
done < <(find . -name conftest.py -not -path './.git/*' 2>/dev/null)
find . \\( -name sitecustomize.py -o -name usercustomize.py \\) -delete 2>/dev/null || true

# Restore pristine original tests and test configuration, then add the hidden tests.
cp -r /tests/regression/. /app/
cp -r /tests/feature/. /app/

timeout 900 bash -c {q(feature_cmd)} > /logs/verifier/feature.log 2>&1
timeout 1800 bash -c {q(regression_cmd)} > /logs/verifier/regression.log 2>&1

python3 /tests/grade.py /tests/expected.json /logs/verifier/feature.xml \\
  /logs/verifier/regression.xml /logs/verifier/reward.json || true
exit 0
"""


def build_verifier_dockerfile(env_dockerfile: str) -> str:
    """Same toolchain and dependencies as the agent environment, plus the verifier files."""
    return (env_dockerfile.rstrip() + "\n\n"
            "COPY test.sh grade.py expected.json /tests/\n"
            "COPY feature/ /tests/feature/\n"
            "COPY regression/ /tests/regression/\n")


def write_tests(
    task_dir: Path,
    task: GeneratedTask,
    profile: RepositoryProfile,
    adapter: LanguageAdapter,
    snapshot: Path,
    env_dockerfile: str,
    regression_paths: list[str],
) -> None:
    tests_dir = task_dir / "tests"
    fs.rmtree(tests_dir)
    tests_dir.mkdir(parents=True)
    for tf in task.feature_test_files:
        fs.write_text_lf(fs.resolve_inside(tests_dir / "feature", tf.path), tf.content)
    pristine = pristine_test_files(snapshot)
    for rel, content in pristine.items():
        fs.write_text_lf(fs.resolve_inside(tests_dir / "regression", rel), content)
    (tests_dir / "regression").mkdir(exist_ok=True)
    conftests = sorted(p for p in pristine if p.endswith("conftest.py"))
    fs.write_text_lf(tests_dir / "test.sh", build_test_sh(
        adapter, [t.path for t in task.feature_test_files], regression_paths, conftests),
        executable=True)
    grade = resources.files("codeforge.harbor.templates").joinpath("grade.py").read_text(
        encoding="utf-8")
    fs.write_text_lf(tests_dir / "grade.py", grade)
    fs.write_text_lf(tests_dir / "expected.json", json.dumps({
        "feature_tests": task.feature_test_ids,
        "regression_tests": task.regression_test_ids,
        "starting_commit_sha": task.starting_commit_sha,
    }, indent=2))
    # Verifier build context: the pristine repository (for dependencies) + verifier files.
    shutil.copytree(snapshot, tests_dir / "repo",
                    ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "node_modules"))
    fs.write_text_lf(tests_dir / "Dockerfile", build_verifier_dockerfile(env_dockerfile))
    fs.write_text_lf(tests_dir / ".dockerignore", "**/__pycache__\n**/*.pyc\n")
