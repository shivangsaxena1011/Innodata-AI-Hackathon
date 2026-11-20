# Submission checklist

Status as of 2026-11-20. ✅ = present and verified by running it · ⏳ = pending · ⚠️ = partial

| # | Requirement (hackathon) | Where | Status |
|---|---|---|---|
| 1 | Runnable source code | `src/codeforge/` (CLI `python -m codeforge.main`, dashboard `serve`) | ✅ |
| 2 | Setup and execution instructions | `README.md` (Quickstart, CLI), `scripts/setup.ps1`, `scripts/setup.sh` | ✅ clean install tested |
| 3 | Sample generated tasks | `generated_tasks/shopcart/` (4), `generated_tasks/cachetools/` (1) | ✅ |
| 4 | Harbor task packages | each task dir: `task.toml`, `instruction.md`, `environment/`, `solution/`, `tests/` | ✅ `harbor lint` clean, oracle 1.0, nop 0.0 |
| 5 | Reference implementations | `solution/solve.sh` + `solution/reference.patch` per task | ✅ |
| 6 | Feature and regression tests | `tests/feature/` (hidden), `tests/regression/` (pristine originals), `tests/expected.json` | ✅ |
| 7 | Validation evidence | `validation/validation.json` + logs per task; `reports/<run>/` | ✅ |
| 8 | Mutation-testing reports | `validation.json` → `mutation_result`, `semantic_mutation_result`; dashboard Validation tab | ✅ |
| 9 | Cross-task variation evidence | `reports/cross_task_validation.json` (4×4: 4/4 diagonal pass, 12/12 off-diagonal fail); `reports/cross_task_validation_5x5.json` (5×5: 5/5 pass, 20/20 fail) | ✅ |
| 10 | Architecture documentation | `docs/architecture.md`, `docs/technology-decisions.md`, `docs/security.md` | ✅ |
| 11 | Third-party licenses and notices | `THIRD_PARTY_NOTICES.md`, `licenses/`, `third_party/manifest.yaml`, `docs/source-integration-manifest.md`, `docs/upstream-research.md` | ✅ |
| 12 | Demo instructions | `docs/final-demo-script.md`, `docs/demo-guide.md` | ✅ |
| — | Final results summary | `reports/final-results.md` | ✅ |
| — | Project audit | `reports/final_project_audit.md` | ✅ |
| — | Real AI-agent benchmark | `reports/benchmark.md` (written by the scheduled run) | ⏳ scheduled 2026-11-20 14:00 IST |
| — | Run on the Innodata-supplied repository | `codeforge run <repo>` | ⏳ repository not provided |
| — | Second language end to end | JavaScript adapter | ⚠️ analysis only so far |

## Before submitting
1. Decide whether to ship the LLM response cache. The current `.gitignore` ignores
   `.codeforge_cache/`. Un-ignore `.codeforge_cache/llm/` if judges should replay generations
   without an API key.
2. Review the uncommitted changes from the final audit (`git status`), then commit them.
3. Optionally build a clean bundle: `uv run python scripts/build_submission.py`. It writes
   `dist/codeforge-ai-submission.zip`, excluding `.env`, `.venv`, `workspace/` and caches.
4. When the Innodata repository arrives:
   ```
   uv run python -m codeforge.main analyze <repo>
   uv run python -m codeforge.main run <repo> --prepare-only
   uv run python -m codeforge.main run <repo> -n 3
   ```
   Report its results separately from the sample results.
5. Push to GitHub yourself (CodeForge's tooling never pushes).
