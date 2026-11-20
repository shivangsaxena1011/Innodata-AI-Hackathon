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
2. **Contract-First Specification**: Emits an observable interface contract (functions, classes, CLI flags, HTTP routes) that defines the boundary without leaking implementation or test logic.
3. **Independent Dual-Path Generation**: Generates the hidden test suite and reference patch in completely isolated model calls from the specification only, ensuring tests are never overfitted to the reference solution.
4. **Adversarial Multi-Gate Validation**: Enforces six rigorous execution gates in fresh Docker sandboxes (RED, GREEN, REGRESSION, MUTATION, STABILITY, CONTRACT) to eliminate vacuous, brittle, or non-discriminative tasks.
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
                      │ E. Validation Engine │  RED ──▶ GREEN ──▶ REGRESSION ──▶
                      └──────────┬───────────┘  MUTATION ──▶ STABILITY ──▶ CONTRACT
                                 ▼
                      ┌──────────────────────┐
                      │  F. Harbor Packager  │  Canonical Harbor task skeleton,
                      └──────────┬───────────┘  oracle verification (reward = 1.0)
                                 ▼
                      ┌──────────────────────┐
                      │ G. Reporting & UI    │  evidence.json, suite HTML dashboard,
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
* **MUTATION Gate**: Plausible mutant solutions (simulating realistic agent blunders via AST mutation and semantic errors) must be killed (≥1 test failure) by the feature tests.
* **STABILITY Gate**: Execution of tests across 3 consecutive iterations must yield identical deterministic results.
* **CONTRACT Gate**: Static check verifying that tests only reference approved symbols in the interface contract.
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
│   └── sample_target_repository # `tiny_cart` / `shopcart` Python reference target repo
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
   ```

3. **Configure environment variables**:
   ```bash
   cp .env.example .env
   # Add your Gemini API key (free tier supported)
   ```

4. **Verify environment readiness**:
   ```bash
   uv run python -m codeforge.main doctor
   ```

5. **Run test suite**:
   ```bash
   uv run pytest tests/unit -q
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
uv run python -m codeforge.main analyze examples/sample_target_repository
```

### 3. `codeforge run [repo] [options]`
Generates and adversarially validates Harbor tasks end-to-end:
```bash
# Generate 2 tasks on the bundled sample repository
uv run python -m codeforge.main run sample -n 2

# Generate tasks on a custom Git repository at a specific branch or commit
uv run python -m codeforge.main run https://github.com/org/repo.git --ref main -n 3
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
Runs an agent against the complete suite of validated tasks and writes a benchmark performance report:
```bash
uv run python -m codeforge.main benchmark --agent nop
```

### 6. `codeforge serve`
Launches the interactive real-time monitoring web dashboard:
```bash
uv run python -m codeforge.main serve --port 8765
```

---

## 🌐 Interactive Web Dashboard

CodeForge includes a lightweight, real-time web dashboard (built with FastAPI and pure modern frontend, requiring no node/npm build step):
- **Live Pipeline Visualizer**: View active and completed task generation stages.
- **Validation Gate Matrix**: Real-time breakdown of RED, GREEN, REGRESSION, MUTATION, and STABILITY results.
- **Evidence Explorer**: Interactive inspector for `evidence.json`, diffs, test logs, and JUnit XML traces.
- **Task Launcher**: Trigger task generation runs with custom model and archetype parameters directly from the browser.

---

## 💰 Zero-Cost Model Architecture & Caching

CodeForge is engineered for **zero marginal cost**:
- **Gemini Free Tier Rotation**: Rotates through Google Gemini free-tier models (`gemini-flash-latest`, `gemini-3.5-flash`, `gemini-2.5-flash`, etc.) to stay within daily rate limits without incurring cost.
- **Local Ollama Fallback**: Automatic offline fallback to local models (`llama3.2`) if API access is unavailable or quota is exceeded.
- **Deterministic Disk Cache**: All LLM completions are cached by prompt hash and parameters under `.codeforge_cache/llm`, ensuring 100% reproducible re-runs without extra model requests.

---

## 👥 Authors & Team

Developed with ❤️ by **Team TECH TITAN**:
- **Shivang Saxena** ([@shivangsaxena1011](https://github.com/shivangsaxena1011))
- **Rani Malviya**

For the **Innodata AI Hackathon 2026** (Track 1: Coding Task Factory).

---

## 📜 License

This project is licensed under the **Apache License 2.0** - see the [LICENSE](LICENSE) file for details.  
Third-party component notices and licenses are documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
