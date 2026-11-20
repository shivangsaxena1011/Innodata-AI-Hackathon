# CodeForge AI: development notes for Claude Code

Innodata AI Hackathon 2026, Track 1 (Coding Task Factory). Team TECH TITAN: Shivang Saxena,
Rani Malviya. Submissions are due 6 Dec 2026.

## What this is
A Python 3.12 pipeline that turns a real Git repository into validated Harbor
feature-development tasks. The entry point is `src/codeforge/pipeline.py`; the CLI is
`codeforge` (`src/codeforge/main.py`); the dashboard is `codeforge serve` (`src/codeforge/web/`).

## Commands
- Tests: `.venv/Scripts/python.exe -m pytest tests/unit -q -p no:cacheprovider`
- Lint: `.venv/Scripts/python.exe -m ruff check src tests`
- Environment check: `.venv/Scripts/python.exe -m codeforge.main doctor`
- Full run on the bundled sample: `.venv/Scripts/python.exe -m codeforge.main run sample -n 2`
- Environment + baseline only (no LLM): `... codeforge.main run <repo> --prepare-only`
- 4×4 cross-task matrix from packages: `... codeforge.main crosscheck shopcart`
- Agent benchmark: `... codeforge.main benchmark --agent gemini-cli --repo shopcart` (`--agent nop` = control)
- Submission bundle: `uv run python scripts/build_submission.py` → `dist/`
- Use `python -m pytest`, not `pytest.exe` (Windows Application Control blocks uv launchers)
- Dashboard: `.venv/Scripts/python.exe -m codeforge.main serve --port 8765`

## Machine constraints (Windows)
- Windows Smart App Control blocks uv-downloaded Python, so the venv is built on the signed
  system Python 3.12: `uv venv --python <path to python3.12>`.
- Harbor 0.26.0 is installed with `uv tool install harbor` at `~/.local/bin/harbor.exe`;
  run it from PowerShell or through `harbor_validator.harbor_executable()`.
- Docker Desktop provides the Linux engine. WSL is not needed.
- Write every file that ends up in a container with `utils.fs.write_text_lf` (LF only).

## Rules
- Never fabricate results. Every gate status must come from an executed run (Docker or Harbor).
- Never run target-repo or generated code on the host; use `DockerSandbox`.
- Never put secrets in packages; `leakage_checker` enforces this.
- The bundled `examples/sample_target_repository` is a development sample. It is NOT the
  Innodata repository, and the docs and UI must keep saying so.
- Free of cost: the default model is Gemini's free tier, rotated across free Flash models
  because each is limited to 20 requests per day, with Ollama as the local fallback.
  LLM responses are cached in `.codeforge_cache/llm`, so re-runs reproduce exactly.
- Do not create or initialise a GitHub repo. The user owns the repo and will provide its
  link at the end.
- Keep third-party attribution current: `THIRD_PARTY_NOTICES.md`,
  `third_party/manifest.yaml`, `docs/source-integration-manifest.md`.
