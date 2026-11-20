"""Anti-shortcut and leakage checks on a finished Harbor package."""

from __future__ import annotations

import os
import re
from pathlib import Path

from codeforge.schemas.task import GeneratedTask

SECRET_PATTERNS = [re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), re.compile(r"sk-[A-Za-z0-9]{20,}"),
                   re.compile(r"ghp_[A-Za-z0-9]{30,}")]


def check_package(task_dir: Path, task: GeneratedTask) -> list[str]:
    problems: list[str] = []
    instruction = (task_dir / "instruction.md").read_text(encoding="utf-8")
    env_dir = task_dir / "environment"

    # 1. Instruction must not reveal hidden tests or verifier internals.
    for name in task.feature_test_ids:
        leaf = name.split("::")[-1]
        if len(leaf) > 8 and leaf in instruction:
            problems.append(f"instruction mentions hidden test name {leaf}")
    for marker in ("/tests", "test.sh", "solve.sh", "/solution", "reward.json", "grade.py"):
        if marker in instruction:
            problems.append(f"instruction mentions verifier/solution path {marker!r}")
    for tf in task.feature_test_files:
        if Path(tf.path).name in instruction:
            problems.append(f"instruction mentions hidden test file {tf.path}")

    # 2. Reference code must not appear in the instruction or the agent environment.
    added_lines = [line[1:].strip() for line in task.reference.unified_diff.splitlines()
                   if line.startswith("+") and not line.startswith("+++")]
    # Text the spec deliberately discloses (contract signatures, requirements) is not a leak.
    disclosed = " ".join(" ".join(c.signature.split()) for c in task.spec.contract)
    disclosed += " " + " ".join(task.spec.model_dump_json().split())
    distinctive = [line for line in added_lines if len(line) >= 40 and
                   " ".join(line.split()) not in disclosed]
    for line in distinctive[:200]:
        if line in instruction:
            problems.append(f"instruction contains reference code: {line[:60]}")
            break
    for ch in task.reference.changes:
        env_file = env_dir / "repo" / ch.path
        if env_file.exists() and env_file.read_text(encoding="utf-8") == ch.content:
            problems.append(f"agent environment already contains the reference version of "
                            f"{ch.path}")
    for tf in task.feature_test_files:
        if (env_dir / "repo" / tf.path).exists():
            problems.append(f"hidden test {tf.path} is present in the agent environment")

    # 3. No git history, no copied tests/solution in the agent image build context.
    if (env_dir / "repo" / ".git").exists():
        problems.append("agent environment contains .git history")
    dockerfile = (env_dir / "Dockerfile").read_text(encoding="utf-8")
    if re.search(r"COPY\s+.*(tests/|solution/)", dockerfile) and "COPY repo/" not in dockerfile:
        problems.append("agent Dockerfile copies tests or solution")

    # 4. No secrets anywhere in the package.
    secret_values = [v for k, v in os.environ.items()
                     if any(h in k.upper() for h in ("KEY", "TOKEN", "SECRET")) and len(v) >= 12]
    for path in task_dir.rglob("*"):
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(v in text for v in secret_values) or any(p.search(text) for p in SECRET_PATTERNS):
            problems.append(f"possible secret in {path.relative_to(task_dir).as_posix()}")
    return problems
