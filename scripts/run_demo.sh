#!/usr/bin/env bash
# End-to-end demo: generate and validate tasks on the bundled sample repository
# (a CodeForge development sample, NOT the Innodata-supplied repository), then serve the UI.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run codeforge doctor
uv run codeforge analyze sample
uv run codeforge run sample --tasks "${TASKS:-2}"
uv run codeforge serve --port "${PORT:-8000}"
