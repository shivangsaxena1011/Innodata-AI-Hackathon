# Demo guide (about 8 minutes)

Before the demo: Docker Desktop running, `.env` containing `GEMINI_API_KEY`, and
`uv run codeforge doctor` all green. For a reliable live demo, run once beforehand: cached
model responses make the second run reproduce exactly and quickly.

## 1. The problem (30 s)
AI coding benchmarks need tasks that are realistic, solvable and impossible to shortcut.
CodeForge builds them from a real repository and proves each one with executed evidence.

## 2. Dashboard (1 min)
`uv run codeforge serve` → http://127.0.0.1:8000
- The header shows live Docker, Harbor and model status.
- The hero stats come from real validated tasks on disk.

## 3. Analyze (1 min)
In **Forge**, keep `sample` (state clearly: *our sample repository, not the Innodata
repository*) and click **Analyze**:
- pinned commit, language, test framework, adapter
- extension points, and the token-budgeted ranked repository map (Aider-style PageRank)

## 4. Forge live (3 min)
Click **Forge** (Harbor on). Narrate the stepper as it moves:
- **Docker env / Baseline**: the original suite runs 3× in a network-less container.
- **Discovery**: candidates across archetypes; duplicates and existing names are rejected,
  with the reason shown.
- **Spec → Hidden tests ‖ Reference**: separate model calls; the tests never see the solution.
- **Red · Green**: tests fail on the original code and pass with the reference; regression
  and stability are checked.
- **Mutation**: diff-scoped AST mutants plus plausible wrong implementations.
- **Harbor**: `harbor lint`, then the oracle trial (reward 1.0) and the no-op trial
  (reward 0.0).

If time is short, open a task generated earlier instead of waiting.

## 5. Inspect a task (2 min)
Click a task card:
- **Overview**: exactly what the agent sees (requirements, acceptance criteria, interface
  contract).
- **Validation**: every gate with its real result, mutation bars, coverage, oracle and nop
  rewards, and the score breakdown with its rules.
- **Reference**: the diff. **Hidden tests**: the file plus requirement → test traceability.
- **Download package**: a Harbor task ready for `harbor run -p . -a <agent>`.

## 6. Terminal proof (30 s)
```bash
cd generated_tasks/shopcart/<task_id>
harbor lint .
harbor run -p . -a oracle
```

## 7. Close (30 s)
Anti-shortcut design: no git history, separate verifier, pristine tests restored, planted
hooks removed. Everything runs for free on Gemini's free tier or Ollama, and every result
comes from execution.
