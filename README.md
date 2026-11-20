# CodeForge AI

> **A coding task factory that turns real repositories into validated Harbor feature-development benchmark tasks.**  
> Built by **Team TECH TITAN** (**Shivang Saxena** & **Rani Malviya**) for the **Innodata AI Hackathon 2026** (Track 1: Coding Task Factory).

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![Built with uv](https://img.shields.io/badge/managed%20by-uv-orange.svg)](https://github.com/astral-sh/uv)
[![Harbor Framework](https://img.shields.io/badge/target-Harbor%20Framework%200.26.0-blueviolet.svg)](https://docs.harborframework.com)
[![Docker](https://img.shields.io/badge/sandbox-Docker%20Container-2496ED.svg)](https://www.docker.com/)

---

## 🚀 Overview

**CodeForge AI** automates the generation of rigorous, reproducible, and discriminative coding benchmark tasks from real-world Git repositories. Targeting the canonical **Harbor** task interface (Harbor 0.26.0), CodeForge extracts codebase architecture, identifies extension seams, synthesizes complete feature specifications with explicit interface contracts, generates independent reference solutions and hidden tests in isolated model calls, and adversarially validates every task inside isolated Docker containers before publishing.

### 🌟 Core Strategy: Contract-First Feature Synthesis with Adversarial Validation

1. **Seam & Archetype Identification**: Identifies high-cohesion, low-churn extension points and pairs them with distinct behaviour archetypes.
2. **Contract-First Specification**: Emits an observable interface contract (functions, methods, classes, constants, exception types) that defines the boundary without leaking implementation or test logic.
3. **Independent Dual-Path Generation**: Generates the hidden test suite and reference patch in completely isolated model calls from the specification only, ensuring tests are never overfitted to the reference solution.
4. **Adversarial Multi-Gate Validation**: Executed gates in fresh Docker sandboxes (RED, GREEN, REGRESSION, STABILITY, MUTATION, SEMANTIC MUTANTS) plus static INDEPENDENCE and LEAKAGE checks reject vacuous, brittle or non-discriminative tasks. Surviving mutants become counter-examples that strengthen the hidden tests.
5. **Canonical Harbor Packaging**: Emits standard Harbor task packages (`instruction.md`, `task.toml`, `environment/Dockerfile`, `solution/solve.sh`, `tests/test.sh`) verified via `harbor lint` and `harbor run -a oracle` (reward 1.0) and `harbor run -a nop` (reward 0.0).

---

## 🏗️ Architecture & Pipeline Flow

```
                      ┌──────────────────────┐
       Target Repo ──▶│   A. Repo Intake     │  Clone, pin full commit SHA, fingerprint
                      └──────────┬───────────┘
                                 ▼
                      ┌──────────────────────┐   Build once per (repo, sha)
                      │   B. Env Builder     │──▶ Docker sandbox, baseline test runs (N=3),
                      └──────────┬───────────┘  flaky test filtering, shortcut detection
                                 ▼
                      ┌──────────────────────┐
                      │  C. Repo Analyzer    │  py-tree-sitter AST, PageRank repo map,
                      └──────────┬───────────┘  symbol extractor & extension point ranking
                                 ▼
                      ┌──────────────────────┐  D1: Plan (archetype × seam, novelty check)
                      │  D. Task Synthesis   │  D2: Specification + Interface Contract
                      └──────────┬───────────┘  D3: Hidden Tests ┐ Independent calls
                                 │              D4: Reference    ┘ from spec only
                                 │              D5: Plausible Mutants (AST + LLM)
                                 ▼
                      ┌──────────────────────┐
                      │ E. Validation Engine │  RED ──▶ GREEN ──▶ REGRESSION ──▶ STABILITY
                      └──────────┬───────────┘  ──▶ MUTATION ──▶ strengthening ⟲ repair loop
                                 ▼
                      ┌──────────────────────┐
                      │  F. Harbor Packager  │  Canonical Harbor task skeleton,
                      └──────────┬───────────┘  oracle verification (reward = 1.0)
                                 ▼
                      ┌──────────────────────┐
                      │ G. Reporting & UI    │  validation.json, HTML report, dashboard,
                      └──────────────────────┘  discrimination & variation matrix
```

---

## 🎯 Behaviour Archetypes

To ensure meaningful diversity across generated task suites, CodeForge enforces coverage across seven distinct behaviour archetypes:

| Archetype | Description | Example Pattern |
|---|---|---|
| **Business Rule** | New validation, constraint, or policy logic | Enforce discount eligibility thresholds & promo code stacking rules |
| **State Machine** | New entity lifecycle state with legal transitions | Add a "partially refunded" order state and transition guards |
| **Query / Aggregation** | Multi-dimensional grouping, filtering, or metrics | Compute revenue and tax by category across date intervals |
| **Configuration / Policy** | Pluggable strategies or configuration schemas | Introduce currency-specific rounding algorithms |
| **Component Interaction** | Cross-module coordination or event dispatch | Link customer loyalty accrual to checkout discount tiers |
| **Error Handling** | Robust failure recovery and typed exception domains | Typed error hierarchies and actionable diagnostic messages |
| **Interface Extension** | Exposing underlying capabilities via new endpoints/CLI | Add a new CLI subcommand or REST route mapping existing logic |

---

## 🛡️ Adversarial Validation Gates

Every candidate task must pass all gates in isolated Docker containers; failure triggers a bounded repair loop or rejection:

* **RED Gate**: The hidden feature tests must fail against the baseline unpatched codebase.
* **GREEN Gate**: The hidden feature tests must pass (100%) when the reference patch is applied.
* **REGRESSION Gate**: All previously passing baseline tests must continue to pass without failure.
* **STABILITY Gate**: Execution of tests across 3 consecutive iterations must yield identical deterministic results.
* **MUTATION Gate**: Diff-scoped AST mutants (only lines the reference changed: comparisons, arithmetic, constants, enum swaps, collection entries, deleted calls, ...) must reach a kill rate of at least 60%.
* **SEMANTIC MUTANTS Gate**: Plausible wrong implementations written by the model must be caught (warning below 100%, failure below 50%).
* **INDEPENDENCE Check**: Every acceptance criterion traced to at least one test; no private or implementation-only imports, no skips, no assertion-free tests.
* **HARBOR Gates**: `harbor lint` clean, oracle reward 1.0, no-op (`nop`) reward 0.0.
* **LEAKAGE & SHORTCUT Checks**: Automated scans ensure no secrets, test implementations, or synthetic shortcuts leak into the agent environment.

---

## 📁 Repository Layout

```
.
├── src/codeforge/               # Main package
│   ├── adapters/                # Ecosystem & testing adapters (Python, JavaScript/Node, etc.)
│   ├── ai/                      # LLM client (Gemini free rotation + Ollama), prompt manager, cache
│   ├── config.py                # Pydantic Settings & environment config
│   ├── discovery/               # Extension point scoring, ranking & novelty checker
│   ├── environment/             # Docker sandbox builder, environment validator & shortcuts scanner
│   ├── evaluation/              # Agent runner & test execution result parsers (JUnit XML)
│   ├── generation/              # Spec, test, patch, and mutant synthesis
│   ├── harbor/                  # Harbor package generator, grader template & harbor validator
│   ├── logging_config.py        # Structured logging
│   ├── main.py                  # CLI entrypoint (Typer)
│   ├── pipeline.py              # End-to-end task generation & validation orchestration DAG
│   ├── reporting/               # Evidence manager, HTML suite report & variation matrix
│   ├── repository/              # Git manager, AST parser, PageRank repo mapper, language detector
│   ├── schemas/                 # Strict Pydantic models (repository, task, validation)
│   ├── utils/                   # File system & subprocess helpers (LF enforcement)
│   ├── validation/              # Multi-gate validation engine & repair loop
│   └── web/                     # Interactive monitoring web dashboard (FastAPI + Vanilla JS)
├── docs/                        # Architecture & design documentation
│   ├── architecture.md          # Complete pipeline and system architecture (implemented 0.1.0)
│   ├── demo-guide.md            # Interactive walkthrough and live demonstration guide
│   ├── development-roadmap.md   # Phased implementation roadmap & milestones
│   ├── security.md              # Container isolation, credential handling & network policy
│   ├── source-integration-manifest.md # Upstream lineage and technical references
│   └── technology-decisions.md  # Architectural Decision Records (ADRs)
├── examples/                    # Offline fixture repositories
│   └── sample_target_repository # `shopcart`: CodeForge's own sample repo (NOT the Innodata repository)
├── generated_tasks/             # Emitted Harbor task packages (sample set verified)
│   └── shopcart/
├── licenses/                    # Component & dependency licenses (Harbor, Aider, py-tree-sitter, etc.)
├── prompts/                     # Structured prompt templates (task, test, reference, mutant, discovery)
├── reports/                     # Task execution evidence & HTML reports
├── scripts/                     # Developer & automation scripts (demo, setup, validation)
├── tests/                       # Unit, integration, and security test suites
├── .env.example                 # Environment configuration template
├── pyproject.toml               # Project dependencies and tool settings
├── README.md                    # Project documentation
├── THIRD_PARTY_NOTICES.md       # Third-party notices and open-source attributions
└── uv.lock                      # Deterministic dependency lockfile
```

---

## ⚡ Quickstart & Setup

### Prerequisites

- **Python**: `>= 3.12`
- **uv**: Fast Python package manager ([install guide](https://docs.astral.sh/uv/getting-started/installation/))
- **Docker**: Docker Desktop (or Linux Docker daemon) for isolated execution
- **Git**: `>= 2.40`
- **Harbor CLI**: (`uv tool install harbor`) for Harbor packaging and verification

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/shivangsaxena1011/Innodata-AI-Hackathon.git
   cd Innodata-AI-Hackathon
   ```

2. **Set up the virtual environment with uv**:
   ```bash
   uv sync
   uv tool install harbor   # if Harbor is not installed yet
   ```
   > Windows: if Smart App Control blocks uv's downloaded Python, run
   > `uv venv --python "<path to a python.org Python 3.12>\python.exe"` and then `uv sync`.

3. **Configure environment variables**:
   ```bash
   cp .env.example .env
   # Put your free Gemini API key in GEMINI_API_KEY (https://aistudio.google.com/apikey).
   # CodeForge exports .env into the process environment for LiteLLM and Harbor agents.
   ```

4. **Verify environment readiness**:
   ```bash
   uv run python -m codeforge.main doctor
   ```

5. **Run test suite**:
   ```bash
   uv run python -m pytest tests/unit -q          # 55 unit tests
   uv run python -m pytest tests/integration -q   # Docker + Harbor (needs Docker)
   ```

---

## 💻 CLI Usage

CodeForge AI provides a comprehensive CLI powered by Typer:

### 1. `codeforge doctor`
Checks system prerequisites: Docker daemon connectivity, Harbor 0.26.0 CLI, and active LLM configuration.
```bash
uv run python -m codeforge.main doctor
```

### 2. `codeforge analyze <repo>`
Profiles target repository using py-tree-sitter and PageRank symbol extraction without running Docker or LLMs:
```bash
uv run python -m codeforge.main analyze sample          # bundled sample (deterministic commit)
uv run python -m codeforge.main analyze https://github.com/tkem/cachetools
```

### 3. `codeforge run [repo] [options]`
Generates and adversarially validates Harbor tasks end-to-end:
```bash
# Generate 2 tasks on the bundled sample repository
uv run python -m codeforge.main run sample -n 2

# Generate tasks on a custom Git repository at a specific branch or commit
uv run python -m codeforge.main run https://github.com/org/repo.git --ref main -n 3

# Only build the environment and run the baseline 3x (no model calls)
uv run python -m codeforge.main run https://github.com/msiemens/tinydb --prepare-only
```

### 4. `codeforge evaluate <task_dir>`
Benchmarks an AI coding agent on a single validated task using Harbor:
```bash
# Evaluate with oracle reference solution
uv run python -m codeforge.main evaluate generated_tasks/shopcart/add-order-refund-and-return-lifecycle-states-059169 --agent oracle

# Negative control: evaluate with nop (no-operation) agent
uv run python -m codeforge.main evaluate generated_tasks/shopcart/add-order-refund-and-return-lifecycle-states-059169 --agent nop
```

### 5. `codeforge benchmark`
Runs an agent against every validated task (optionally one repository) and writes `benchmark.json` + `benchmark.md`. A task counts as solved only on verifier reward 1.0; quota and infrastructure errors are listed separately:
```bash
uv run python -m codeforge.main benchmark --agent nop --repo shopcart          # control: reward 0.0
uv run python -m codeforge.main benchmark --agent gemini-cli --repo shopcart   # real agent, free Gemini tier
```

### 6. `codeforge crosscheck`
Runs every task's hidden tests against every task's reference (N x N) using only the shipped packages:
```bash
uv run python -m codeforge.main crosscheck shopcart   # writes reports/cross_task_validation.json
uv run python -m codeforge.main crosscheck all --out reports/cross_task_validation_5x5.json
```

### 7. `codeforge serve`
Launches the interactive real-time monitoring web dashboard:
```bash
uv run python -m codeforge.main serve --port 8765
```

---

## 🌐 Interactive Web Dashboard

CodeForge includes a lightweight, real-time web dashboard (built with FastAPI and pure modern frontend, requiring no node/npm build step):
- **Analyze**: repository profile, pinned commit, extension points and the ranked repository map.
- **Forge (task launcher)**: start a run (repository, ref, number of tasks, Harbor on/off) and watch every pipeline stage and event live.
- **Task gallery**: validity score, gate status and mutation score per task.
- **Task inspector**: agent instruction, every gate with its executed result, mutation and coverage, reference diff, hidden tests with requirement traceability, `task_manifest.json` / `task.toml`, and package download.

---

## 💰 Zero-Cost Model Architecture & Caching

CodeForge is engineered for **zero marginal cost**:
- **Gemini Free Tier Rotation**: Rotates through Google Gemini free-tier models (`gemini-flash-latest`, `gemini-3.5-flash`, `gemini-2.5-flash`, etc.) to stay within daily rate limits without incurring cost.
- **Local Ollama Fallback**: Automatic offline fallback to local models (`llama3.2`) if API access is unavailable or quota is exceeded.
- **Deterministic Disk Cache**: All LLM completions are cached by prompt hash and parameters under `.codeforge_cache/llm`, so re-running the same pipeline on the same machine replays the same generations without extra model requests. (The cache is git-ignored; commit `.codeforge_cache/llm/` to make clones replayable.)
- **Free-tier reality**: Gemini's free tier allows about 20 requests per model per day. One task needs about 6-12 calls, and a real agent benchmark needs many more.

---

## 📊 Results (executed, not estimated)

> The Innodata-supplied repository has not been provided yet. Headline results use
> **CodeForge's own sample repository** (`shopcart`), which is **not** the Innodata
> repository. Full details and evidence links: [reports/final-results.md](reports/final-results.md).

**Sample repository**: 4 validated Harbor tasks, all with oracle reward **1.0**, no-op reward
**0.0** and `harbor lint` clean:

| Task | Archetype | Hidden tests | Validity | AST mutants killed | Semantic mutants |
|---|---|---|---|---|---|
| Support promotional discount codes in cart pricing | business rule | 10 | 98.5 | 80% | 4/4 |
| Add order refund and return lifecycle states | state machine | 7 | 99.2 | 89.5% | 4/4 |
| Add inventory valuation and stock report aggregation | query / aggregation | 7 | 95.7 | 92% | 2/4 |
| Add volume-based discount configuration policy | configuration policy | 13 | 99.2 | 90% | 4/4 |

**Cross-task validation:**
- `codeforge crosscheck shopcart`: every reference passes its own tests (**4/4**) and fails
  all **12/12** other combinations ([4×4](reports/cross_task_validation.json)).
- Across all five shipped packages (`codeforge crosscheck all`): **5/5** on the diagonal, and
  **20/20** off-diagonal combinations fail (12/12 same-repository, 8/8 cross-repository)
  ([5×5](reports/cross_task_validation_5x5.json)).

**Generalization on public repositories:**
- **cachetools** (MIT): a VALID task was generated, validity 100, 8 hidden tests protecting
  476 existing tests, oracle 1.0 / nop 0.0.
- **TinyDB** (MIT): environment and 227-test baseline OK; the generated task was honestly
  **rejected** after 3 repair attempts.
- **clsx** (JS, MIT): analysed; execution reported **unsupported** (`uvu` test runner).

**Real AI-agent benchmark**: pending, not executed yet, and no agent results are claimed.
The free Gemini quota was exhausted, so a one-time run with Harbor's `gemini-cli` agent is
scheduled after the daily reset; its results will appear in `reports/benchmark.md`. Oracle
validation (reference solution, reward 1.0 on all 5 packages) and agent results are kept separate.

**CodeForge's own tests**: 55 unit tests + 3 Docker/Harbor integration tests pass; a
clean-install test was run ([audit](reports/final_project_audit.md)).

## ⚠️ Honest limitations

- **Languages**: Python repositories are supported end to end. JavaScript is supported for
  analysis; the Node execution adapter (node:test / vitest / jest) has not run on a real JS
  repository yet. AST mutation is Python-only; other languages rely on semantic mutants.
- **Free-tier quota**: about 20 requests per model per day. Large batches and agent
  benchmarks need several days or more models. Ollama (`llama3.2`) is only a weak fallback.
- **Model strength**: harder features can be rejected (for example the TinyDB atomic-validation
  task). Rejection is the intended outcome when evidence is missing.
- **Target dependency pinning**: base images are digest-pinned, but target dependencies are
  installed from the repository's own specs, which may resolve differently later.
- **Validity score**: a transparent heuristic summary; the executed gates are the proof.

## 👥 Authors & Team

Developed with ❤️ by **Team TECH TITAN**:
- **Shivang Saxena** ([@shivangsaxena1011](https://github.com/shivangsaxena1011))
- **Rani Malviya**

For the **Innodata AI Hackathon 2026** (Track 1: Coding Task Factory).

---

## 📜 License

This project is licensed under the **Apache License 2.0** - see the [LICENSE](LICENSE) file for details.  
Third-party component notices and licenses are documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
