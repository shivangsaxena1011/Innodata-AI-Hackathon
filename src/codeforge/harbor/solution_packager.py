"""solution/solve.sh: writes the reference file contents (base64, so any content survives
shell quoting and line-ending conversion) into the agent's working copy."""

from __future__ import annotations

import base64
import shlex
from pathlib import Path

from codeforge.schemas.task import ReferenceSolution
from codeforge.utils import fs


def build_solve_sh(reference: ReferenceSolution, workdir: str = "/app") -> str:
    lines = ["#!/bin/bash", "# CodeForge reference solution (oracle).", "set -euo pipefail",
             f"cd {workdir}"]
    for i, ch in enumerate(reference.changes):
        rel = shlex.quote(fs.safe_relpath(ch.path))
        b64 = base64.b64encode(ch.content.encode("utf-8")).decode("ascii")
        wrapped = "\n".join(b64[j:j + 76] for j in range(0, len(b64), 76))
        lines += [f"mkdir -p \"$(dirname {rel})\"",
                  f"base64 -d > {rel} <<'CODEFORGE_EOF_{i}'", wrapped, f"CODEFORGE_EOF_{i}"]
    lines.append('echo "reference solution applied"')
    return "\n".join(lines) + "\n"


def write_solution(task_dir: Path, reference: ReferenceSolution) -> None:
    sol = task_dir / "solution"
    sol.mkdir(parents=True, exist_ok=True)
    fs.write_text_lf(sol / "solve.sh", build_solve_sh(reference), executable=True)
    fs.write_text_lf(sol / "reference.patch", reference.unified_diff)
