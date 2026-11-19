# CodeForge — Technology Decisions

Each entry gives the decision, the reason, and the alternatives we rejected. Versions get pinned in `pyproject.toml` / `uv.lock` once we have installed and tested them. None are installed yet.

## Core

| Area | Decision | Why | Rejected / notes |
|---|---|---|---|
| Language | **Python ≥ 3.12** | Harbor's `pyproject.toml` requires ≥3.12. The brief said 3.11+, so 3.12 satisfies both. | 3.11 can't install Harbor in the same environment |
| Host OS | **WSL2 Ubuntu** plus Docker Desktop | Harbor, SWE-smith and SWE-bench target Linux, and the tasks use bash scripts. SWE-smith explicitly does not support Windows. | Native Windows: undocumented for Harbor, with CRLF and path risks |
| Packaging | **uv** | Fast, gives a lockfile, and is what Harbor's docs use. Already installed (0.11.25). | pip/venv |
| Task interface | **Harbor** (Apache-2.0) | It is the required interface. We use its CLI for skeleton creation (`harbor task init`) and validation (`harbor run -a oracle`), and do not re-implement its runner. | — |
| Models | **LiteLLM** | The organiser's model provider is still unknown. LiteLLM gives one API across providers and tracks cost. | Locking to one provider's SDK before we know the credits |
| Structured output | **Pydantic v2** (+ pydantic-settings) | Every model output must fit a schema, and failures can be retried. It also covers typed config. | Free-text parsing |
| Agent framework | **None at first** | The pipeline is a fixed DAG, so an agent framework adds dependencies without adding capability. We revisit only if the repair loop needs tool calling. | Pydantic AI, LangChain |
| Git | **Git CLI via subprocess** | Exact SHA handling, no extra dependency, easy to log. | GitPython (a thin wrapper over the CLI anyway) |
| Docker | **Docker CLI via subprocess** in a small `sandbox.py` wrapper | Harbor already drives Docker this way. The logs are plain commands, and it behaves the same under WSL. | docker-py: possible later, if we need streaming control |
| CLI | **Typer** | Harbor uses it, and it is small. | argparse (fine too) |

## Code understanding

| Area | Decision | Why |
|---|---|---|
| Parsing | **py-tree-sitter** + **tree-sitter-language-pack** | One API across many languages, so the analysis works even if the supplied repo is not Python. |
| Repo map | **Our own, following Aider's approach**: `tags.scm` def/ref queries and a networkx PageRank within a token budget | Proven to pick the context that matters. We adapt the idea and reuse no code beyond permissively licensed query files (licence to be checked per file). |
| Whole-repo dump | Not used in the pipeline | Gitingest is fine for poking around by hand, but it wastes tokens and gives no structure. |

## Testing and validation

| Area | Decision | Why |
|---|---|---|
| Target test results | **JUnit XML** wherever the framework can emit it | One language-agnostic parser, giving test IDs for FAIL_TO_PASS and PASS_TO_PASS. |
| Python targets | pytest, **pytest-cov / coverage.py**, **mutmut** on lines the patch changed | Coverage shows the reference code is exercised. mutmut adds mutation evidence that doesn't depend on a model. |
| All targets | **LLM-generated semantic mutants** | Works in any language, and the mutants are *plausible* bugs, which is what an agent actually gets wrong. |
| Property tests | **Hypothesis**: optional, for Python targets with numeric or collection rules | Useful for edge cases, but it is non-deterministic, so it runs with a fixed seed (`derandomize=True`). |
| CodeForge's own tests | pytest | — |

## Prior art we borrow ideas from (no code dependency)

| Project | What we take |
|---|---|
| **SWE-bench** | FAIL_TO_PASS / PASS_TO_PASS vocabulary; Docker evaluation per instance; log parsers. |
| **SWE-smith** (MIT) | Turning a repo into a Docker environment; *validate by execution and keep only instances that break ≥1 test*; LLM-written issue text. We work in the **opposite direction**: they add bugs, we add features. |
| **SWE-Gym** | Lesson: building the environment is the bottleneck, so invest in recipes and baseline stability early. |
| **Harbor `adapters/swebench`** | The package shape: a gold patch in `solve.sh` applied with `patch -p1`, and `test.sh` writing the reward from F2P/P2P results. `adapters/swesmith` and `adapters/swegym` are also worth reading. |
| **Aider** | The repo map design, as described above. |
| Worth a look, not yet reviewed | FEA-Bench and SWE-Dev, feature-implementation benchmarks that are closer to our task type. |

## Security and keys
- Keys only come from the environment or `.env` (gitignored). We ship `.env.example`.
- Generated code runs only inside containers, with CPU and memory limits and no network where the stack allows.
- Prompts include the repo's code, so the run log records which provider received it.

## Pending verification (Phase 0)
- [ ] Which `task.toml` schema (`schema_version` 1.4 vs `version` 1.0) the installed Harbor accepts.
- [ ] Whether `reward.json` needs a `reward` key for aggregation.
- [ ] What `harbor lint` checks, so we can run it on every emitted task.
- [ ] Harbor behaviour on WSL2 with Docker Desktop.
