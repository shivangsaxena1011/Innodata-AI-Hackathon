#!/usr/bin/env bash
# Quality gate for CodeForge itself: lint, unit tests, Docker/Harbor integration tests,
# and `harbor lint` over every generated task package.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run ruff check src tests
uv run pytest tests/unit -q
uv run pytest tests/integration -q -m "docker or harbor" || echo "integration tests skipped/failed (needs Docker + Harbor)"
for t in generated_tasks/*/*/task.toml; do
  [ -e "$t" ] || continue
  harbor lint "$(dirname "$t")"
done
