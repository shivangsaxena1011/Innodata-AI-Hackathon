# CodeForge AI

> **A coding task factory that turns real repositories into validated Harbor feature-development benchmark tasks.**  
> Built by **Team TECH TITAN** (**Shivang Saxena** & **Rani Malviya**) for the **Innodata AI Hackathon 2026**.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![Built with uv](https://img.shields.io/badge/managed%20by-uv-orange.svg)](https://github.com/astral-sh/uv)
[![Harbor Framework](https://img.shields.io/badge/target-Harbor%20Framework-blueviolet.svg)](https://docs.harborframework.com)

---

## 🚀 Overview

**CodeForge AI** automates the generation of rigorous, reproducible, and discriminative coding benchmark tasks from real-world Git repositories. Targeting the **Harbor** task interface, CodeForge extracts codebase architecture, identifies extension seams, synthesizes complete feature specifications with explicit interface contracts, generates independent reference solutions and tests, and adversarially validates every task inside isolated Docker containers before publishing.

### Core Strategy: Contract-First Feature Synthesis with Adversarial Validation

1. **Seam & Archetype Identification**: Identifies high-cohesion, low-churn extension points and pairs them with distinct behaviour archetypes.
2. **Contract-First Specification**: Emits an observable interface contract (functions, classes, CLI flags, HTTP routes) that defines the boundary without leaking implementation or test logic.
3. **Independent Generation**: Generates the hidden test suite and reference patch in isolated model calls from the specification only.
4. **Adversarial Multi-Gate Validation**: Enforces six rigorous execution gates in a fresh Docker sandbox to eliminate vacuous, brittle, or non-discriminative tasks.
5. **Canonical Harbor Packaging**: Packages approved tasks into standard Harbor format (`instruction.md`, `task.toml`, `environment/Dockerfile`, `solution/solve.sh`, `tests/test.sh`) verified via `harbor run -a oracle`.

---

## 🏗️ Architecture & Pipeline Flow

```
                      ┌──────────────────────┐
       Target Repo ──▶│   A. Repo Intake     │  Clone, pin full commit SHA, fingerprint
                      └──────────┬───────────┘
                                 ▼
                      ┌──────────────────────┐   Build once per (repo, sha)
                      │   B. Env Builder     │──▶ Docker sandbox, baseline test runs (N=3),
                      └──────────┬───────────┘  flaky test filtering
                                 ▼
                      ┌──────────────────────┐
                      │  C. Repo Analyzer    │  Tree-sitter AST, PageRank repo map,
                      └──────────┬───────────┘  test inventory & extension points
                                 ▼
                      ┌──────────────────────┐  D1: Plan (archetype × seam)
                      │  D. Task Synthesis   │  D2: Specification + Interface Contract
                      └──────────┬───────────┘  D3: Hidden Tests ┐ Independent calls
                                 │              D4: Reference    ┘ from spec only
                                 │              D5: Plausible Mutants
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
                      │    G. Reporting      │  Per-task evidence.json, suite report,
                      └──────────────────────┘  discrimination & variation matrix
```

---

## 🎯 Behaviour Archetypes

To ensure diversity across generated task suites, CodeForge enforces coverage across seven distinct behaviour archetypes:

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

## 🛡️ Validation Gates

Every candidate task must pass all gates in isolated Docker containers; failure triggers a bounded repair loop or rejection:

* **RED Gate**: The hidden feature tests must fail against the baseline unpatched codebase.
* **GREEN Gate**: The hidden feature tests must pass (100%) when the reference patch is applied.
* **REGRESSION Gate**: All previously passing baseline tests must continue to pass without failure.
* **MUTATION Gate**: Plausible mutant solutions (simulating realistic agent blunders) must be killed (≥1 test failure) by the feature tests.
* **STABILITY Gate**: Execution of tests across 3 consecutive iterations must yield identical deterministic results.
* **CONTRACT Gate**: Static check verifying that tests only reference approved symbols in the interface contract.

---

## 📁 Repository Layout

```
.
├── src/codeforge/               # Main package
│   ├── adapters/                # Ecosystem & testing adapters (Python, Node, etc.)
│   ├── ai/                      # LLM integration & prompt templates
│   ├── config.py                # Pydantic Settings & environment config
│   ├── discovery/               # Extension point scoring & planning
│   ├── environment/             # Docker sandbox & recipe builder
│   ├── evaluation/              # Test execution & result parsers (JUnit XML)
│   ├── generation/              # Spec, test, and patch synthesis
│   ├── harbor/                  # Harbor package generator & runner
│   ├── logging_config.py        # Structured logging
│   ├── reporting/               # Evidence reports, HTML summaries & variation matrix
│   ├── repository/              # Git manager, AST parser, PageRank repo mapper
│   ├── schemas/                 # Pydantic models (repository, task, validation)
│   ├── utils/                   # File system & subprocess helpers
│   ├── validation/              # Validation gates & repair loop
│   └── web/                     # Web/API monitoring interface
├── docs/                        # Architecture & design documentation
│   ├── architecture.md          # Complete pipeline and system architecture
│   ├── development-roadmap.md   # Phased implementation roadmap & milestones
│   └── technology-decisions.md  # Architectural Decision Records (ADRs)
├── examples/                    # Offline fixture repositories
│   └── sample_target_repository # `tiny_cart` Python reference target repo
├── generated_tasks/             # Emitted Harbor task packages
├── licenses/                    # Component & dependency licenses
├── prompts/                     # Structured prompt templates
├── reports/                     # Task execution evidence & reports
├── research/                    # Upstream research & prior art notes
├── scripts/                     # Developer & automation scripts
├── tests/                       # Unit, integration, and E2E test suites
├── .env.example                 # Environment configuration template
├── pyproject.toml               # Project dependencies and tool settings
├── README.md                    # Project documentation
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
   # Add your model API key (e.g. GEMINI_API_KEY)
   ```

4. **Run offline tests**:
   ```bash
   uv run pytest
   ```

---

## 👥 Authors & Team

Developed with ❤️ by **Team TECH TITAN**:
- **Shivang Saxena** ([@shivangsaxena1011](https://github.com/shivangsaxena1011))
- **Rani Malviya**

Innodata AI Hackathon 2026.

---

## 📜 License

This project is licensed under the **Apache License 2.0** - see the `pyproject.toml` for details.
