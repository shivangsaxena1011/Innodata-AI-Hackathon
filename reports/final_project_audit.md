# CodeForge AI: final project audit

Audit date: 2026-11-20. Scope: the whole repository, read-only first, then targeted fixes.
Every finding below was checked by running the code or reading the source. Status is one of
**Fixed**, **Open** (documented limitation) or **OK** (verified, no action needed).

## 1. Inventory

| Item | Value |
|---|---|
| CodeForge package | `src/codeforge`: 72 Python modules, ~6.3k lines; dashboard ~720 lines of HTML/CSS/JS |
| Tests | 55 unit tests (`tests/unit`), 3 Docker + Harbor integration tests (`tests/integration`) |
| Generated task packages | 4 on the bundled sample (`generated_tasks/shopcart/`), plus generalization tasks on public repos (`generated_tasks/cachetools/`, `generated_tasks/tinydb/` when valid) |
| Toolchain verified | Python 3.12, uv 0.11.25, Docker 29.9.3 (Linux engine), Harbor 0.26.0, Git 2.56 |
| Git | Branch `main` tracking `origin/main` (GitHub). 4 commits by the user before this audit; this audit left its changes **uncommitted** for review. Nothing was pushed. |

## 2. Findings

| # | Area | Finding | Status |
|---|---|---|---|
| A1 | README vs CLI | `codeforge analyze examples/sample_target_repository` failed: that folder is plain files, and CodeForge requires a git commit to pin. | **Fixed**: the bundled sample's path is now an alias for `sample` (`pipeline.resolve_source`); the README uses `analyze sample`. |
| A2 | Setup | `.env` was read only for `CODEFORGE_*` settings. `GEMINI_API_KEY` in `.env` never reached LiteLLM or Harbor's agents, so a clean install following the README would have no model access. | **Fixed**: `config.load_dotenv()` exports `.env` without overriding existing variables (names only, never values, are logged). Unit test added. |
| A3 | Quota handling | The exhausted-model list was keyed by the UTC date, but Gemini resets at midnight Pacific, so refreshed models stayed skipped for up to 13.5 h after the reset. | **Fixed**: keyed by the Pacific date (`LLMClient.quota_day`). |
| A4 | Harbor on Windows | Long Harbor job names overflowed the 260-character path limit when Harbor copied the `/app` artifact (`FileNotFoundError` in the benchmark). | **Fixed**: all trials use `workspace/hj/<agent>-<hash>`; new packages exclude `*.egg-info` from the artifact. The system long-path setting was not changed. |
| A5 | CLI | `evaluate --agent oracle/nop` passed a model id to agents that take none. | **Fixed**: the model is dropped for control agents (the command already worked; it is now clean). |
| A6 | Dashboard security | The API bound to 127.0.0.1 but accepted any `Host` header, so it was exposed to DNS-rebinding pages. | **Fixed**: `TrustedHostMiddleware` (localhost, 127.0.0.1, [::1]). Unit test added. |
| A7 | Benchmark evidence | The benchmark recorded no tokens, agent time or verifier details. | **Fixed**: tokens in/out, cost, agent time, model info and the grader's `grading.json` are recorded per trial. |
| A8 | README claims | The rewritten README claimed: a separate "CONTRACT gate" (actually part of the INDEPENDENCE gate); CLI flags and HTTP routes as contract kinds (only function/method/class/constant/exception exist); a dashboard that picks model and archetype and shows JUnit traces (it does not); "≥1 kill" mutation rule (the gate uses a 60% threshold); 100% reproducible re-runs (the LLM cache is git-ignored). It also lost the results, limitations and the "sample is not the Innodata repo" disclaimer. | **Fixed**: claims corrected; results, limitations and generalization sections restored. |
| A9 | Windows launchers | `uv run pytest` was blocked by Windows Application Control (unsigned `pytest.exe` launcher) in the clean-install test. | **Fixed (docs)**: commands use `python -m pytest` / `python -m codeforge.main`, which work. |
| A10 | Reproducibility | `.gitignore` ignores `.codeforge_cache/`, so a fresh clone cannot replay cached generations without an API key. | **Open (user decision)**: the user's `.gitignore` was kept. Un-ignore `.codeforge_cache/llm/` to ship replayable generations. |
| A11 | Dependency pinning in target images | Target dependencies are installed with the repository's own specs (`pip install -e .`, `-r requirements*.txt`). Unpinned upstream specs can resolve differently on a later build. Base images *are* digest-pinned. | **Open (documented)**: Harbor lint does not flag it; a lock-file-aware installer would be the next step. |
| A12 | Agent network | Harbor agent containers use `network_mode = "public"` because real agents must reach their model API; the verifier is `no-network`. | **OK (by design)** |
| A13 | Mutation for JavaScript | AST mutation is Python-only; JS relies on semantic mutants. The JS execution adapter has not run on a real JS repository (clsx uses `uvu`, which is unsupported). | **Open (documented)** |
| A14 | Real-agent benchmark | Not executed in this session: the free Flash quotas (20 requests/model/day) were exhausted. A one-time run is scheduled for 2026-11-20 14:00 IST, after the 13:30 IST reset. | **Open (scheduled)**: status re-checked 2026-11-20 11:16 IST: 0 runs yet, not started manually to avoid a duplicate job. |
| A15 | Innodata repository | Not supplied. Nothing in the project or the hackathon material provides it. | **Open (external)** |
| A16 | Path safety | Hypothesis found that `safe_relpath(".")` (or `"./"`) raised `IndexError` instead of `UnsafePathError`, because `"."` has no path parts. A model-supplied `"."` path would have crashed an edit instead of being rejected. | **Fixed**: empty-part paths are rejected; regression cases added (55 unit tests). |

## 3. Secrets and personal data
A scan of all 2,318 tracked files plus new untracked files found:
- **No** occurrence of any real API key or token value (compared against the environment
  inside Python; values never printed).
- **No** key-shaped strings (`AIza…`, `sk-…`, `ghp_…`).
- **No** personal machine paths (Windows user profile, temp folders) and **no** email
  addresses.

## 4. Security review (Phase 5)

| Control | Result |
|---|---|
| Docker isolation for validation | OK: `--network none`, memory/CPU/PID limits, `--cap-drop ALL`, `no-new-privileges`, tmpfs `/tmp`, no bind mounts, container always removed (`docker_builder.run_script`) |
| Generated-code execution | OK: only inside containers; host-side work is parsing (tree-sitter, tomllib) and `git archive` |
| Host filesystem | OK: model-supplied paths pass `safe_relpath` / `resolve_inside`; tar `data` filter; zip-slip and symlink checks |
| Network | OK: validation has no network; Harbor verifier `no-network`; image builds need network for dependency installs (documented) |
| Environment variables | OK: containers start with an empty environment; only Harbor's agent receives the provider key it needs |
| API-key protection | OK: log redaction filter, leakage scanner on every package, repository-wide scan above |
| Subprocess | OK: argument lists only, `shell=False` enforced, `shlex.quote` for in-container scripts |
| Temporary cleanup | OK: staging dirs are `TemporaryDirectory`; containers removed in `finally`. Note: Docker images and `workspace/hj` job dirs accumulate (disk, not security) |
| Version pinning | OK: full commit SHA, digest-pinned base image, deterministic sample commit `e4eee2fd…` |
| CodeForge dependencies | OK: exact pins in `pyproject.toml` + `uv.lock` |
| Hidden-test separation | OK: tests only in `tests/` (separate verifier container), agent image scanned for test/solution/.git/secrets |
| Reference leakage | OK: instruction scanned against reference code (contract text excluded), `solution/` only reaches the oracle |
| Verifier tampering | OK: pristine tests and config restored, agent-added `conftest.py` / `sitecustomize.py` removed, reward written first |
| Dashboard | Fixed (A6) |

## 5. Clean-installation test (Phase 6)
The test used a fresh copy of exactly the files a clone would get (no `.venv`, caches,
`workspace/` or `.env`):

| Step | Result |
|---|---|
| `uv sync` | OK: environment created from `uv.lock` |
| `uv run python -m codeforge.main doctor` | OK: Docker 29.9.3, Harbor 0.26.0, key present |
| `uv run python -m codeforge.main analyze sample` | OK: same deterministic commit `e4eee2fdf7755a6ffef7253e9b11621f85fd92f2` |
| `uv run python -m pytest tests/unit -q` | OK: 52 passed (`uv run pytest` was blocked by Windows Application Control, see A9) |
| `uv run python -m pytest tests/integration -q` | OK: 3 passed (real Docker and Harbor oracle/nop) |
| `uv run python -m codeforge.main serve` | OK: index 200, `/api/tasks` lists the packaged tasks |

## 6. Experimental or untested features
- JavaScript execution adapter (`adapters/languages/javascript_adapter.py`): analysis works;
  execution has not run on a real JS repository.
- Ollama fallback (`ollama/llama3.2`): configured as the last fallback, but no task was
  generated with it (3B models are weak at code generation).
- `codeforge evaluate` / `benchmark` with real agents: plumbing is verified with `oracle`
  (reward 1.0) and `nop` (4/4 graded, reward 0.0); the real Gemini run is pending (A14).
