# Final demo script: CodeForge AI (≈ 8 minutes)

Team TECH TITAN: Shivang Saxena, Rani Malviya.

## Before the demo (15 minutes earlier)
```powershell
cd "C:\Users\Project\Innodata AI Hackathon"
uv run python -m codeforge.main doctor                 # Docker, Harbor 0.26.0, key present
uv run python -m codeforge.main serve --port 8765      # leave running
```
- Open http://127.0.0.1:8765. The header dots for Docker, Harbor and Model should be green.
- Have a second terminal open in the project folder.
- Optional warm-up: `uv run python -m codeforge.main analyze sample` (no model calls).
- **Do not** start a new live generation unless free quota is available today. Gemini's free
  tier allows about 20 requests per model per day. The existing packages and evidence are
  the demo.

## 1. The problem (30 s)
"AI coding benchmarks need feature tasks that are realistic, solvable and impossible to
shortcut. CodeForge turns a real repository into Harbor tasks and accepts a task only when
executed evidence proves it."

## 2. Analyze a repository (1 min)
In the dashboard, keep the Forge repository as **`sample`** and click **Analyze**.
Say clearly: *"This is our own sample repository, not the Innodata repository."*
Point out the pinned commit `e4eee2fd…`, the detected language, test framework and adapter,
the extension points, and the token-budgeted ranked repository map (Aider-style PageRank).

## 3. The pipeline (1.5 min)
Scroll to **How it works** and walk the stages:
- **Understand**: pin the commit, parse with tree-sitter, Docker environment, baseline ×3.
- **Generate**: spec with an interface contract, then hidden tests and the reference in
  separate model calls.
- **Prove**: RED, GREEN, regression, stability, diff-scoped mutation, semantic mutants and
  test strengthening.
- **Package**: Harbor task with a separate verifier: `harbor lint` clean, oracle 1.0,
  no-op 0.0.

If quota is available, click **Forge** (1 task, Harbor on) and let the stepper run in the
background while you continue.

## 4. Inspect a validated task (2 min)
Open **Support promotional discount codes in cart pricing**:
- **Overview**: exactly what the agent sees (requirements, acceptance criteria, contract).
- **Validation**: every gate executed, 12/15 AST mutants killed, 4/4 semantic mutants,
  100% changed-line coverage, oracle 1 / nop 0, and the score breakdown with its rules.
- **Reference**: the diff. **Hidden tests**: the test file plus requirement → test
  traceability.
- Mention test strengthening: "the first tests let 8 mutants survive; CodeForge fed them back
  and adopted tests that kill 16 instead of 11."

## 5. Proof in the terminal (1.5 min)
```powershell
uv run python -m codeforge.main crosscheck shopcart
```
This prints the 4 × 4 matrix: diagonal **pass 4/4**, off-diagonal **fail 12/12**. Each task
tests different behaviour. (~2 minutes; it can be run beforehand, and the matrix is also in
`reports/cross_task_validation.json`.)

```powershell
cd generated_tasks\shopcart\add-order-refund-and-return-lifecycle-states-059169
harbor lint .
harbor run -p . -a oracle      # reward 1.0 (~70 s)
```

## 6. Generalization (45 s)
Open `reports/final-results.md` §4:
- **cachetools** (a real MIT library): a valid task, 8 hidden tests protecting 476
  existing tests.
- **TinyDB**: honestly rejected after 3 repair attempts.
- **clsx** (JavaScript): reported unsupported.

"We report rejections and unsupported cases; we never fake a pass."

## 7. Close (30 s)
- **Anti-shortcut design:** no git history in the agent image, separate verifier container,
  pristine tests restored, planted pytest hooks removed, no secrets.
- **Free of cost:** Gemini free tier plus Ollama fallback, all responses cached.
- **Real-agent benchmark:** report it from `reports/benchmark.md` if the scheduled run has
  completed. Otherwise say it is pending because of the free quota.

## If something goes wrong
- Dashboard dots red → start Docker Desktop; run `doctor`.
- A live run fails on quota → that is shown honestly in the console; switch to the existing tasks.
- Browser shows an old layout → hard refresh (Ctrl+F5); assets are cache-busted per version.
