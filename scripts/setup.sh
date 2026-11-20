#!/usr/bin/env bash
# CodeForge AI setup for Linux/macOS. Free of cost: Gemini free tier + optional Ollama.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv --python 3.12
uv sync
command -v harbor >/dev/null || uv tool install harbor
[ -f .env ] || { cp .env.example .env; echo "Created .env: add GEMINI_API_KEY"; }
uv run codeforge doctor
