"""Build a clean hackathon submission bundle: dist/codeforge-ai-submission/ + .zip.

Includes exactly what a git clone would contain (tracked and new, non-ignored files), so
.env, .venv, workspace/ and caches are excluded by .gitignore. Refuses to finish if any file
contains a real secret value from the environment or a key-shaped string.

usage: uv run python scripts/build_submission.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "codeforge-ai-submission"
KEY_SHAPES = re.compile(r"AIza[0-9A-Za-z_\-]{30,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}")


def files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return sorted(f for f in out.split("\0") if f and not f.startswith("dist/"))


def main() -> int:
    secrets = [v for k, v in os.environ.items()
               if any(h in k.upper() for h in ("KEY", "TOKEN", "SECRET")) and len(v) >= 12]
    if OUT.exists():
        shutil.rmtree(OUT)
    problems, copied = [], 0
    for rel in files():
        if Path(rel).name == ".env":
            problems.append(f"refusing to include {rel}")
            continue
        src = ROOT / rel
        if not src.is_file():
            continue
        data = src.read_bytes()
        text = data.decode("utf-8", errors="ignore")
        if any(s in text for s in secrets) or KEY_SHAPES.search(text):
            problems.append(f"possible secret in {rel}")
            continue
        dest = OUT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        copied += 1
    if problems:
        print("\n".join(problems))
        return 1
    zip_path = OUT.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(OUT.rglob("*")):
            if p.is_file():
                zf.write(p, Path(OUT.name) / p.relative_to(OUT))
    size = zip_path.stat().st_size / 1e6
    print(f"bundle: {OUT} ({copied} files)\nzip:    {zip_path} ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
