"""Safe subprocess execution: argument lists only, timeouts, captured output, no shell."""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from codeforge.logging_config import redact

log = logging.getLogger(__name__)


@dataclass
class ProcResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_sec: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @property
    def output(self) -> str:
        return (self.stdout or "") + (self.stderr or "")


class CommandError(RuntimeError):
    def __init__(self, result: ProcResult, message: str = "command failed"):
        tail = redact(result.output[-2000:])
        cmd = " ".join(result.args[:6])
        super().__init__(f"{message}: {cmd} (exit {result.returncode})\n{tail}")
        self.result = result


def run(
    args: list[str],
    cwd: Path | str | None = None,
    timeout: float | None = 600,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
    check: bool = False,
) -> ProcResult:
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise TypeError("run() requires a list of string arguments (no shell strings)")
    start = time.monotonic()
    log.debug("run: %s", " ".join(args))
    try:
        cp = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            shell=False,
        )
        result = ProcResult(args, cp.returncode, cp.stdout, cp.stderr, time.monotonic() - start)
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        result = ProcResult(args, -1, out, err, time.monotonic() - start, timed_out=True)
    except FileNotFoundError as exc:
        result = ProcResult(args, 127, "", str(exc), time.monotonic() - start)
    if check and not result.ok:
        raise CommandError(result)
    return result
