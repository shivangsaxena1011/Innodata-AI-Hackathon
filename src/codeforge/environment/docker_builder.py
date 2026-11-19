"""Docker sandbox. All target-repository and generated code runs here, never on the host.

Isolation defaults: no network, CPU/memory/PID limits, all Linux capabilities dropped,
no-new-privileges, no host bind mounts (files move in and out with `docker cp`), and no
Docker socket inside the container.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from codeforge.config import Settings, get_settings
from codeforge.utils import fs
from codeforge.utils.proc import CommandError, ProcResult, run

log = logging.getLogger(__name__)


class DockerUnavailable(RuntimeError):
    pass


@dataclass
class SandboxRun:
    result: ProcResult
    out_dir: Path
    container_log: Path


class DockerSandbox:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self.bin = self.s.docker_bin

    def _d(self, args: list[str], timeout: float = 600, check: bool = True) -> ProcResult:
        return run([self.bin, *args], timeout=timeout, check=check)

    def version(self) -> str | None:
        r = run([self.bin, "version", "--format", "{{.Server.Version}} {{.Server.Os}}"],
                timeout=30)
        return r.stdout.strip() if r.ok else None

    def require(self) -> None:
        if not self.version():
            raise DockerUnavailable("Docker engine is not reachable; start Docker Desktop")

    def pin_image(self, ref: str) -> str:
        """Resolve a tag such as python:3.12-slim to an immutable `repo@sha256:...` reference."""
        if "@sha256:" in ref:
            return ref
        inspect = self._d(["image", "inspect", "--format", "{{json .RepoDigests}}", ref],
                          check=False, timeout=60)
        if not inspect.ok or inspect.stdout.strip() in ("[]", "null", ""):
            self._d(["pull", "-q", ref], timeout=900)
            inspect = self._d(["image", "inspect", "--format", "{{json .RepoDigests}}", ref],
                              timeout=60)
        digests = re.findall(r"[\w./-]+@sha256:[0-9a-f]{64}", inspect.stdout)
        if not digests:
            raise CommandError(inspect, f"could not resolve a digest for {ref}")
        name, digest = digests[0].split("@")
        short = ref.split(":")[0]
        return f"{short}:{ref.split(':')[1]}@{digest}" if ":" in ref else f"{name}@{digest}"

    def image_exists(self, tag: str) -> bool:
        return self._d(["image", "inspect", tag], check=False, timeout=60).ok

    def build(self, context: Path, tag: str, log_path: Path | None = None) -> ProcResult:
        result = self._d(
            ["build", "--label", "codeforge=1", "-t", tag, str(context)],
            timeout=self.s.build_timeout_sec, check=False,
        )
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(result.output, encoding="utf-8")
        if not result.ok:
            raise CommandError(result, f"docker build failed for {tag}")
        return result

    def run_script(
        self,
        image: str,
        stage_dir: Path,
        script: str,
        out_dir: Path,
        timeout: float | None = None,
        network: str = "none",
    ) -> SandboxRun:
        """Copy `stage_dir` to /cf in a fresh container, run `script` (bash), and copy /cf/out
        back to `out_dir`. The container is always removed."""
        timeout = timeout or self.s.test_timeout_sec
        fs.write_text_lf(stage_dir / "run.sh", script, executable=True)
        (stage_dir / "out").mkdir(parents=True, exist_ok=True)
        name = f"codeforge-{uuid.uuid4().hex[:12]}"
        create = [
            "create", "--name", name, "--network", network,
            "--memory", self.s.container_memory, "--memory-swap", self.s.container_memory,
            "--cpus", self.s.container_cpus, "--pids-limit", str(self.s.container_pids),
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--tmpfs", "/tmp:rw,exec,size=512m", "--label", "codeforge=1",
            "--entrypoint", "bash", image, "/cf/run.sh",
        ]
        self._d(create, timeout=120)
        try:
            self._d(["cp", f"{stage_dir}{'/' if not str(stage_dir).endswith('/') else ''}.",
                     f"{name}:/cf"], timeout=300)
            result = run([self.bin, "start", "-a", name], timeout=timeout)
            if result.timed_out:
                self._d(["kill", name], check=False, timeout=60)
            out_dir.mkdir(parents=True, exist_ok=True)
            self._d(["cp", f"{name}:/cf/out/.", str(out_dir)], check=False, timeout=300)
            log_file = out_dir / "container.log"
            log_file.write_text(result.output, encoding="utf-8")
            return SandboxRun(result, out_dir, log_file)
        finally:
            self._d(["rm", "-f", name], check=False, timeout=120)
