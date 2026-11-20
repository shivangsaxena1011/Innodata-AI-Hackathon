# Technology decisions

Each entry gives the decision, the reason, and what changed during implementation.

| Area | Decision | Why |
|---|---|---|
| Language | **Python 3.12** (CodeForge itself) | Harbor requires ≥ 3.12. Generated tasks use the target repository's language. |
| Host OS | **Windows + Docker Desktop (Linux engine)**, with no WSL needed | Harbor 0.26.0 runs natively on Windows. The original plan said WSL, but that turned out to be unnecessary. All container-bound files are written with LF endings. |
| Packaging | **uv** + `uv.lock`, exact pins in `pyproject.toml` | Reproducible installs. The venv is built on the signed system Python because Smart App Control blocks uv-downloaded interpreters. |
| Task interface | **Harbor 0.26.0 CLI** (`init`, `lint`, `run -a oracle/nop/<agent>`) | It is the required interface. CodeForge does not re-implement any of it. |
| Verifier mode | **Separate** verifier + `/app` artifact | `harbor lint` flags shared verifiers, and a fresh container ignores anything the agent installed. |
| Models | **LiteLLM** with Gemini free tier, rotated across free Flash models, plus **Ollama** local fallback | Zero cost. The free tier is ~20 requests per model per day, hence the rotation and a per-day exhausted-model list. Any LiteLLM model id works with `--model`. |
| Reproducible generation | Disk cache of every LLM response, keyed by model + prompts + seed | Re-runs replay identical generations; cached and live calls are labelled. |
| Structured output | **Pydantic v2** models + JSON extraction + re-ask with the validation error | Free-form model text is never used unvalidated. |
| Agent framework | None | The pipeline is a fixed DAG with a bounded repair loop, so tool-calling agents would add dependencies without adding capability. |
| Git | Git CLI via `subprocess` (argument lists) | Exact SHA handling. `git archive` gives a history-free snapshot. |
| Docker | Docker CLI via `subprocess` | Same engine path Harbor uses; plain, loggable commands. |
| Parsing | **py-tree-sitter 0.26** + tree-sitter-python/-javascript 0.25 + vendored tags queries | Multi-language. The query API (`Query` + `QueryCursor.captures`) was verified by running it. |
| Repo map | Own re-implementation of Aider's ranking with a built-in PageRank | networkx's PageRank pulls in numpy and scipy; 30 lines of power iteration do the same job. |
| Test results | **JUnit XML** everywhere | Language-agnostic per-test results; stdout can be spoofed, JUnit is read structurally. |
| Mutation | Own diff-scoped AST engine (mutmut operator families) + LLM semantic mutants | mutmut mutates whole modules through its trampoline, while CodeForge needs only the changed lines. Semantic mutants cover non-Python languages. |
| Coverage | coverage.py 7.17.3, in the validation image only | Changed-line coverage evidence without changing the agent's image. |
| Property tests | Hypothesis (CodeForge's own tests) | Invariants: PageRank is a distribution, path safety, mutants always compile. |
| Dashboard | **FastAPI + a static HTML/CSS/JS** frontend (no build step, no framework) | Simple, fast and animated, and it shows only data the API reads from disk. |
| CLI | Typer | Same as Harbor; small. |

## Verified facts (Harbor 0.26.0, by running it)
- `harbor init <org>/<name> --task` scaffolds schema 1.4 with a separate verifier
  (`tests/Dockerfile`).
- `harbor lint <dir> --json` returns `[]` for CodeForge packages. All rules are on except
  `root-agent` and `unpinned-image`.
- `harbor run -p <dir> -a oracle -e docker -o <jobs> --job-name <id>` writes
  `jobs/<id>/<trial>/result.json` with `verifier_result.rewards`.
- The `nop` agent exists and gives the no-change control (reward 0.0 on CodeForge tasks).
- Artifacts are re-materialised at their original `source` path inside the separate
  verifier.
