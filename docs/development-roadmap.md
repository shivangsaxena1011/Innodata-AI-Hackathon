# Development roadmap

Build window: 20 Nov to 6 Dec 2026. Each milestone has a check you can run.

| # | Milestone | Status | Check |
|---|---|---|---|
| 1 | Foundation: project, config, logging, schemas, unit tests | ✅ done | `pytest tests/unit` |
| 2 | Repository intelligence: Git pinning, detection, tree-sitter, repo map | ✅ done | `codeforge analyze sample` |
| 3 | Environment: Docker build, baseline ×3, flaky detection, shortcut scan | ✅ done | `codeforge run sample` → baseline gate |
| 4 | Discovery and task generation with novelty and archetypes | ✅ done | `reports/<run>/discovery.json` |
| 5 | Reference implementation in a throwaway worktree | ✅ done | `generation/patch_generator.py` tests |
| 6 | Independent test generation + traceability + independence checks | ✅ done | INDEPENDENCE gate |
| 7 | Validation engine: RED / GREEN / regression / stability / coverage / mutation + repair | ✅ done | `validation.json` per task |
| 8 | Harbor integration: init, lint, oracle and nop trials | ✅ done | HARBOR_* gates |
| 9 | Dashboard and demo | ✅ done | `codeforge serve` |
| 10 | Run on the Innodata-supplied repository | ⏳ waiting for the repository | `codeforge run <repo>` |
| 11 | Agent benchmark on generated tasks | 🔧 available | `codeforge evaluate <task> --agent aider` |
| 12 | Second ecosystem end to end (JavaScript) | 🔧 experimental adapter | needs a JS target repository |

## When the Innodata repository arrives
1. `codeforge analyze <repo>`: check the language, test framework and adapter.
2. If the adapter says `unsupported`, add a profile in `repository/profiles.py` and an
   adapter in `adapters/languages/`. A `codeforge.toml` override can set test dirs and the
   build command.
3. `codeforge run <repo> -n 3`, then review `reports/<run>/report.html`.
4. Commit the sample packages and evidence for the judges.
