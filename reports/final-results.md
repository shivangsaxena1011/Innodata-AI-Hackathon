# CodeForge AI: final results

Team TECH TITAN (Shivang Saxena, Rani Malviya) · Innodata AI Hackathon 2026, Track 1.
Every number here comes from executed tests in Docker and from Harbor 0.26.0 trials. The
raw evidence is linked from each section. Nothing was edited by hand.

> **Scope:** the Innodata-supplied repository has not been provided. The headline results
> use **CodeForge's own sample repository** (`examples/sample_target_repository`, "shopcart"),
> which is **not** the Innodata repository. Generalization results on public repositories are
> reported separately in section 4.

## 1. Validated Harbor tasks on the sample repository
Repository `shopcart` @ `e4eee2fdf7755a6ffef7253e9b11621f85fd92f2` (deterministic sample commit).

| # | Task | Archetype | Hidden tests | Regression tests | Validity | AST mutants killed | Semantic mutants | Changed-line coverage | Oracle / nop |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Support promotional discount codes in cart pricing | business rule | 10 | 27 | 98.5 | 80% (12/15) | 4/4 | 100% | 1.0 / 0.0 |
| 2 | Add order refund and return lifecycle states | state machine | 7 | 27 | 99.2 | 89.5% | 4/4 | 100% | 1.0 / 0.0 |
| 3 | Add inventory valuation and stock report aggregation | query / aggregation | 7 | 27 | 95.7 | 92% (23/25) | 2/4 | 100% | 1.0 / 0.0 |
| 4 | Add volume-based discount configuration policy | configuration policy | 13 | 27 | 99.2 | 90% (27/30) | 4/4 | 97.1% | 1.0 / 0.0 |

For every task, these gates passed:
- negative control: each hidden test fails on the original code;
- positive control: each hidden test passes with the reference;
- regression: 27/27 original tests still pass;
- stability: three identical runs;
- independence: every acceptance criterion is traced to tests;
- leakage: none found;
- `harbor lint`: no findings.

Tasks 1–3 come from `codeforge run sample -n 3` (run `reports/20261120-001449-shopcart/`).
Task 4 comes from the dashboard's **Forge** button (`reports/20261120-002426-web-2acafa/`).

**What the loops did:**
- **Test strengthening** (task 1): the 8 mutants that survived the first round went back to
  the test generator as counter-examples. The new tests killed 16 mutants instead of 11,
  with every control still passing, so they were adopted.
- **Repair** (task 3): the first reference failed the positive control. The loop
  regenerated only the reference, and attempt 2 passed.
- **Rejections** (earlier runs): tasks whose generated tests misused the existing API were
  rejected. That led to the traceback-based repair diagnosis.

## 2. Cross-task validation: the full 4 × 4 matrix
`codeforge crosscheck shopcart` uses only the shipped packages: tests from `tests/feature/`,
references decoded from `solution/solve.sh`, and the environment from `environment/`.
Saved in [`cross_task_validation.json`](cross_task_validation.json).

| tests \ reference | R1 inventory | R2 refund | R3 volume discount | R4 promo codes |
|---|---|---|---|---|
| **T1** inventory valuation | **pass** | fail | fail | fail |
| **T2** refund lifecycle | fail | **pass** | fail | fail |
| **T3** volume discount | fail | fail | **pass** | fail |
| **T4** promo codes | fail | fail | fail | **pass** |

Each reference passes its own tests (**4/4**) and fails every other task's tests: **12/12**
cross-task combinations fail. The tasks test genuinely different behaviour. They come from
4 distinct archetypes, and the mean pairwise similarity of the 3-task run was 0.045.

## 3. Controls through Harbor (no model involved)

| Check | Result | Evidence |
|---|---|---|
| Oracle agent (reference solution) on every package | reward **1.0**, 4/4 | `validation/validation.json` in each package |
| `nop` agent (no changes) on every package | reward **0.0**, 4/4 graded | `reports/benchmark-20261120-030556-nop/benchmark.md` |
| `codeforge evaluate <refund task> --agent oracle` | solved, reward 1.0 | rerun during the audit |

## 4. Generalization on public repositories (not the Innodata repository)

| Repository | License | Commit | Analysis | Environment + baseline (3 runs) | Task generation |
|---|---|---|---|---|---|
| [tkem/cachetools](https://github.com/tkem/cachetools) | MIT | `c5de5137153b` | python, pytest, `src/` layout | **476** pass, 0 fail, 0 flaky | **VALID**: "Add hit_ratio property to CacheInfo" (query/aggregation). 8 hidden tests protecting 476 regression tests; validity **100**; AST 100%, semantic 4/4, coverage 100%; oracle 1.0 / nop 0.0; the reference also updated the `.pyi` type stub |
| [msiemens/tinydb](https://github.com/msiemens/tinydb) | MIT | `edff96aeb261` | python, pytest, uv-managed | **227** pass, 0 fail, 0 flaky | **REJECTED** (honest): "Add Document Validation Rules". After 3 repair attempts with `gemini-3.1-flash-lite`, the reference still passed only 6/9 hidden tests (atomic validation in `update`/`upsert`/`update_multiple`). No package was shipped. |
| [lukeed/clsx](https://github.com/lukeed/clsx) | MIT | `925494cf31bc` | javascript detected | not attempted | **Unsupported**: tests use `uvu`, which the Node adapter (node:test / vitest / jest) does not cover. Reported, not faked. |

Evidence: `reports/20261120-052818-cachetools/`, `reports/20261120-052944-cachetools/`,
`reports/20261120-052856-tinydb/`, `reports/20261120-053444-tinydb/`, and
`generated_tasks/cachetools/`.

## 5. Agent benchmark (real AI agent)
**Pending, not executed yet.** The real-agent benchmark (Harbor's `gemini-cli` agent on the
free Gemini tier) could not run in this session: every free Flash model had used its daily
quota (`GenerateRequestsPerDayPerProjectPerModel-FreeTier = 20`). A one-time run is scheduled
for **2026-11-20 14:00 IST**, after the 13:30 IST reset:

```
uv run python -m codeforge.main benchmark --agent gemini-cli --repo shopcart \
  --models "gemini/gemini-2.5-flash,gemini/gemini-3.5-flash,gemini/gemini-3.6-flash,gemini/gemini-3.7-flash"
```

When it finishes, it will write `reports/benchmark.json` and `reports/benchmark.md` and
update this section. A task counts as solved only on verifier reward 1.0. Quota and
infrastructure errors are reported separately.

## 6. CodeForge's own test suite

| Suite | Result |
|---|---|
| Unit tests (`python -m pytest tests/unit`) | **52 passed** |
| Integration (`python -m pytest tests/integration`; real Docker + Harbor oracle/nop) | **3 passed** |
| Lint (`ruff check src tests`) | clean |
| Clean install in a fresh copy (`uv sync` → doctor → analyze → tests → serve) | passed (see `final_project_audit.md` §5) |
