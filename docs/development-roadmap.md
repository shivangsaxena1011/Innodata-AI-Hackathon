# CodeForge — Development Roadmap

Build window: **20 Nov – 6 Dec 2026** (17 days). Judging runs 7–14 Dec, and the finale is 20 Dec.
Each phase ends with a **check you can run**, so progress is shown by a passing check rather than a status claim.

---

## Phase 0 — Toolchain and Harbor smoke test (Day 1)
- Start WSL2 Ubuntu, enable Docker Desktop WSL integration, and install `uv` and Python 3.12 inside WSL.
- `uv tool install harbor`, then run the docs quick-start task and a hand-written `hello` task with `-a oracle`.
- Read the remaining Harbor pages: `lint`, `environment`, `instruction`, separate verifier. Settle which `task.toml` schema the installed version accepts.

**Check:** `harbor run -p hello -a oracle` gives reward 1. A deliberately broken `solve.sh` gives reward 0. Record the schema findings in `technology-decisions.md`.

## Phase 1 — Project skeleton and fixture repo (Days 1–2)
- Set up `pyproject.toml`, the CLI skeleton, config, logging and the Pydantic models.
- Build `tests/fixtures/tiny_cart`: a small Python repo we write ourselves (cart, pricing, orders) with its own pytest suite. It is the offline test target and **is not the supplied repo**.

**Check:** `uv run pytest` passes, and `codeforge --help` works.

## Phase 2 — Repo intake and environment builder (Days 2–4)
- Clone, pin the SHA, fingerprint, and squash history.
- Build the Docker image per (repo, SHA). Run the baseline tests 3× and parse JUnit XML into per-test results. Detect flaky tests.
- Write recipes for the Python and Node ecosystems first. When the supplied repo arrives, its recipe becomes priority #1.

**Check:** `codeforge env build <repo>` produces an image and `baseline.json`, with the same results across 3 runs. The integration test runs against `tiny_cart` and one public non-Python repo.

## Phase 3 — Repo analyzer (Days 4–5)
- Extract tree-sitter symbols, build the PageRank repo map within a token budget, and build the test inventory.
- Score extension points.

**Check:** Snapshot tests on `tiny_cart` show the expected symbols, and the repo map fits within the budget. Extension points are produced for both fixture repos.

## Phase 4 — **MVP: one complete validated task** (Days 5–8) ⭐
- D1–D5 synthesis with Pydantic-validated model output.
- Validation gates RED, GREEN, REGRESSION, LLM-MUTATION and STABILITY, plus the repair loop.
- Harbor packager, and oracle, null and mutant Harbor runs.
- `evidence.json` for each task.

**Check:** the MVP acceptance criteria below.

## Phase 5 — Variation and test quality (Days 8–11)
- Archetype-driven planning, duplicate detection, and the cross-task discrimination matrix.
- mutmut on changed lines for Python targets. CONTRACT gate. Coverage of the reference patch.

**Check:** a suite of ≥5 tasks across ≥4 archetypes. The discrimination matrix shows off-diagonal FAIL, and the mutant kill rate is reported for every task.

## Phase 6 — Supplied repo hardening (Days 11–14; starts as soon as the repo arrives)
- Run the full pipeline on the Innodata repo, fix the environment and recipe gaps, and tune the prompts to its conventions.
- Optional: run one real agent with `harbor run -a <agent>` on the suite, to show tasks are solvable but non-trivial.

**Check:** ≥5 validated tasks on the supplied repo, end to end, from one command, with no manual edits.

## Phase 7 — Reporting, demo and submission (Days 14–17)
- HTML/Markdown suite report, README with setup, `make demo`, and a recorded run.
- An honest limitations section and the cost per task.
- Sample `tasks/` and `runs/` committed for judges.

**Check:** a clean clone on a fresh WSL machine runs `make demo` successfully, following only the README.

---

## MVP acceptance criteria (end of Phase 4)

On `tiny_cart`, one command, `codeforge run --repo tests/fixtures/tiny_cart --tasks 1`, must:

1. Record the repo's full commit SHA in `task.toml [metadata]` and in `evidence.json`.
2. Emit **one** Harbor task directory containing `instruction.md`, `task.toml`, `environment/Dockerfile`, `solution/solve.sh` and `tests/test.sh`.
3. State the interface contract in `instruction.md`, without leaking any test code.
4. Show, in `evidence.json`, with logs for each item:
   - RED: every feature test fails on the original code.
   - GREEN: every feature test passes with the reference.
   - REGRESSION: 100% of the baseline-passing original tests still pass.
   - MUTATION: ≥3 plausible mutants, each killed by ≥1 feature test.
   - STABILITY: GREEN gives identical results across 3 runs.
5. Pass `harbor run -p <task> -a oracle` with **reward 1**, and give **reward 0** for the null solution and for each mutant.
6. Run every generated-code execution inside Docker, with no host execution.
7. Keep model keys out of the source tree, loading them only from `.env` or the environment.
8. Make a re-run reproducible: the same plan comes from cached model output, and the validation re-runs give identical results.
9. Pass CodeForge's own unit tests in CI (`uv run pytest`).

## Stretch goals (only after Phase 6)
- Multi-language support, so a second ecosystem runs end to end.
- An agent difficulty calibration score, from k agent attempts per task.
- Multi-step Harbor tasks, where the feature arrives in stages.
