# CodeForge — Architecture

Status: **draft for approval**. Nothing here is implemented yet. "Verified" means checked against official docs or source on 2026-11-20. "To verify" means it must be confirmed by running the real tool before we rely on it.

---

## 1. What CodeForge does

CodeForge is a pipeline. It takes a real Git repository at a pinned commit and produces **Harbor task packages**. Each package asks an AI coding agent to implement a new feature. It also includes a reference implementation and hidden tests, plus evidence that the tests really check the feature.

**One reusable strategy** (the hackathon asks for exactly one):

> **Contract-first feature synthesis with adversarial validation.**
> 1. Pick an extension point in the repo and a *behaviour archetype* (see §6).
> 2. Write a spec. It states the observable **interface contract**: the names, signatures, CLI flags or endpoints the tests will call.
> 3. Generate the tests and the reference implementation **in separate model calls**. Both work from the spec only, so the tests are not tailored to one implementation.
> 4. Validate in a Docker sandbox: the tests must fail on the original code (RED), pass with the reference (GREEN), keep every original test passing (REGRESSION), and catch plausible wrong implementations (MUTATION).
> 5. Package for Harbor, then confirm with Harbor's own oracle run.

Only tasks that pass every gate are emitted. Rejected candidates are logged with the reason. That log is evidence too.

---

## 2. Facts that shape the design

### Harbor task interface (verified from docs.harborframework.com and the GitHub repo)

```
<task>/
├── instruction.md          # what the agent sees
├── task.toml               # config + metadata
├── environment/Dockerfile  # agent sandbox (omittable if task.toml sets environment.docker_image)
├── solution/solve.sh       # reference; run by `-a oracle` (copied to /solution)
└── tests/test.sh           # REQUIRED; uploaded to /tests at verification time
```

- `tests/test.sh` must write `/logs/verifier/reward.txt` (a single number) or `/logs/verifier/reward.json` (labelled numeric metrics; this one wins if both exist).
- **The agent does not see `tests/`.** Tests are uploaded only for verification. That is why the instruction must state the interface contract: without it, the hidden tests would be unfair.
- `task.toml` fields we plan to use: `schema_version`, `[task] name/description/keywords`, `[metadata]` (free-form, so the repo URL, commit SHA and validation summary go here), `[verifier] timeout_sec`, `[agent] timeout_sec`, `[environment] build_timeout_sec/cpus/memory_mb/network_mode`, and `source`.
- Reference validation is `harbor run -p <task> -a oracle`, which must give reward 1.
- Multiple solutions can be selected with `--ae SOLUTION=<n>`, which `solve.sh` reads. We reuse this to run **mutant solutions through Harbor itself** (§5.E).
- Harbor's own `adapters/swebench` is the closest prior art for our package shape. It writes the gold patch in `solve.sh` and applies it with `patch -p1`. Its `test.sh` runs the tests, parses FAIL_TO_PASS and PASS_TO_PASS, and writes the reward. We follow that pattern.
- Harbor needs Python ≥ 3.12 (its `pyproject.toml`) and Docker.

**To verify:**
- The docs show two `task.toml` shapes: `schema_version = "1.4"` with `[task]`, and a tutorial using `version = "1.0"` with `[metadata]`. We generate the skeleton with `harbor task init` and fill it in, rather than hand-writing the schema.
- There is a `harbor lint` page we have not read yet.
- Native Windows support is undocumented.

### Local environment (inspected)

| Item | Found |
|---|---|
| Working directory | empty (no supplied repo yet) |
| Python | 3.12, 3.13, 3.14 (via `py`) |
| uv | 0.11.25 |
| Docker | 29.9.3, Linux engine (Docker Desktop) |
| WSL2 | Ubuntu installed (stopped), plus docker-desktop |
| Git | 2.56 |
| Harbor | **not installed** |

Harbor, SWE-smith and SWE-bench tooling all target Linux. **Decision:** develop and run CodeForge inside **WSL2 Ubuntu**, using Docker Desktop's WSL integration. Windows paths, CRLF line endings and bash `test.sh` scripts are a known source of bugs.

---

## 3. High-level flow

```
            ┌────────────────────┐
 repo URL ──▶ A. Repo Intake      │  clone, pin SHA, fingerprint
 + commit   └─────────┬──────────┘
                      ▼
            ┌────────────────────┐   build once per (repo, sha)
            │ B. Env Builder     │──▶ base image: deps installed, baseline tests run
            └─────────┬──────────┘
                      ▼
            ┌────────────────────┐
            │ C. Repo Analyzer   │  tree-sitter symbols, repo map (PageRank),
            │                    │  test inventory, extension points
            └─────────┬──────────┘
                      ▼
            ┌────────────────────┐
            │ D. Task Synthesis  │  D1 plan (archetype × extension point)
            │   (LLM, Pydantic)  │  D2 spec + interface contract
            │                    │  D3 tests        ┐ independent calls,
            │                    │  D4 reference    ┘ both from the spec only
            │                    │  D5 mutants (plausible-wrong impls)
            └─────────┬──────────┘
                      ▼
            ┌────────────────────┐   all execution in Docker, never on host
            │ E. Validation      │  RED → GREEN → REGRESSION → MUTATION
            │                    │  → STABILITY → (bounded repair loop)
            └─────────┬──────────┘
                      ▼
            ┌────────────────────┐
            │ F. Harbor Packager │  harbor task init → fill → oracle run (reward=1)
            │                    │  → null run (reward=0) → mutant runs (reward=0)
            └─────────┬──────────┘
                      ▼
            ┌────────────────────┐
            │ G. Reporting       │  per-task evidence.json, suite report,
            │                    │  variation matrix, HTML/MD summary
            └────────────────────┘
```

Every stage reads and writes **typed artifacts** (Pydantic models serialised to JSON) under `runs/<run_id>/`. So any stage can be re-run, cached or inspected on its own. That matters for repeatability (25%) and for debugging live in the demo.

---

## 4. Module design

### A. Repo Intake (`codeforge.repo`)
- `clone(url|path, ref) -> RepoSnapshot` uses the Git CLI through `subprocess`. It records the URL, the resolved **full commit SHA**, the branch or tag, and `git describe`.
- Fingerprint: detected languages (by file extension, then tree-sitter), build/test manifests (`pyproject.toml`, `package.json`, `pom.xml`, `go.mod`, `Cargo.toml` and others), and lockfile hashes.
- In the task environment the repo is **history-squashed** at the pinned SHA. The agent cannot read future commits, and the original `.git` contents cannot leak a solution.

### B. Environment Builder (`codeforge.env`)
- Produces a Docker image per `(repo, sha)`: the toolchain, installed dependencies and the repo at `/workspace` (path to be decided against the supplied repo).
- **Recipe detection is layered:**
  1. A recipe from the user or organisers (`codeforge.yaml`), the preferred route.
  2. Heuristics per ecosystem.
  3. An LLM-proposed Dockerfile, validated by building it and running the baseline tests.
- Baseline run: run the full original test suite **3 times**. Record pass/fail per test ID. Tests that are not stable go into `flaky.json` and are excluded from regression checks.
- The output is an `EnvSpec`: image tag, test command, test-ID parser, and the list of baseline-passing tests. The ID parser is a JUnit-XML parser wherever the framework can emit JUnit; this stays language-agnostic.

### C. Repo Analyzer (`codeforge.analysis`)
- Extracts definitions and references with tree-sitter (`tree-sitter-language-pack` grammars and `tags.scm` queries, the same approach as Aider).
- **Repo map**: a graph of files and symbols ranked with PageRank (networkx), with a token budget. It is fed to the model as context; we never paste the whole repo.
- Test inventory: which tests touch which modules, using a coverage map for Python and file-level heuristics elsewhere.
- **Extension points**: public modules with clear seams (registries, dispatch tables, validators, config schemas, CLI subcommands, route tables), well-tested areas, and areas with low churn risk. Each gets a score.

### D. Task Synthesis (`codeforge.synthesis`)
All model output is parsed into Pydantic models, and a call is retried when the output fails the schema.

| Step | Output model | Notes |
|---|---|---|
| D1 Plan | `TaskPlan[]` | One per (archetype, extension point). A dedup check is run against existing features and against other plans. |
| D2 Spec | `TaskSpec` | Title, user story, requirements, **interface contract**, acceptance criteria, edge cases, out-of-scope items, difficulty rationale. |
| D3 Tests | `TestBundle` | Feature tests in the repo's own framework. They touch only the contract. Edge-case tests are tagged. |
| D4 Reference | `Patch` | A unified diff against the pinned SHA. It must not modify the original test files. |
| D5 Mutants | `Patch[]` | 3–5 *plausible but wrong* implementations, each with a written fault hypothesis (for example "threshold uses > instead of ≥", "ignores the stacking rule"). |

D3 and D4 run in separate calls with separate context, and neither sees the other's output. This is the main defence against tests that only check "what this implementation happens to do".

### E. Validation Engine (`codeforge.validation`)
Every run happens in a fresh container from the `EnvSpec` image. No network (where possible), resource limits on, and generated code is never executed on the host.

| Gate | Setup | Pass condition |
|---|---|---|
| **RED** | original code + feature tests | every feature test fails, and import or collection errors are classified separately |
| **GREEN** | reference patch + feature tests | every feature test passes |
| **REGRESSION** | reference patch + baseline-passing original tests | 100% still pass (PASS_TO_PASS) |
| **MUTATION (LLM)** | each D5 mutant + feature tests | each mutant fails ≥1 test; kill rate is reported |
| **MUTATION (mutmut)** | Python targets only, on lines the reference patch changed | mutation score is reported, and the gate threshold is configurable |
| **STABILITY** | GREEN repeated N=3 | identical results |
| **CONTRACT** | static check | tests reference only symbols named in the contract |

If a gate fails, a **bounded repair loop** runs: at most 2 attempts that regenerate the failing part (tests or reference), with the failure log as context. If the gates still fail, the candidate is rejected and the reason is logged. Results are never edited by hand.

### F. Harbor Packager (`codeforge.harbor`)
1. `harbor task init <org>/<slug>` generates the canonical skeleton.
2. Fill it in:
   - `instruction.md`: the spec rendered for agents. It contains the contract and none of the tests.
   - `environment/Dockerfile`: built from the `EnvSpec` with the repo at the pinned SHA.
   - `solution/solve.sh`: writes the reference diff and applies it with `patch -p1` (the swebench-adapter pattern). Mutant branches are selected by `SOLUTION` and kept **only in the evidence copy**, never in the shipped package.
   - `tests/test.sh`: copies the feature tests in, runs feature and regression tests, and writes `reward.json`, e.g. `{"reward": 1, "feature_pass_rate": …, "regression_pass_rate": …}`. The key name is to be verified against Harbor's aggregation.
   - `task.toml`: timeouts, resources, and `[metadata]` with the repo URL, SHA, archetype, CodeForge version and validation summary.
3. **Harbor-native evidence**:
   - `harbor run -a oracle` must give reward 1.
   - A "null" solution (no-op) must give reward 0.
   - Each mutant (`--ae SOLUTION=mutant_k`) must give reward 0.
4. Optional: one real agent run (`harbor run -a claude-code -m <model>`), to show tasks are non-trivial yet solvable.

### G. Reporting (`codeforge.reporting`)
- `evidence.json` per task: every gate, every command, exit codes, test-ID lists, durations, image digests, model and prompt hashes, and token cost.
- A suite report in Markdown and a static HTML page, including the **variation matrix** (§6).
- Every number traces back to a log file. No number is typed by hand.

---

## 5. Data model (sketch)

```python
class RepoSnapshot(BaseModel): url: str; sha: str; languages: list[str]; manifests: dict[str, str]
class EnvSpec(BaseModel): image: str; test_cmd: list[str]; parser: Literal["junit", "pytest", ...]; baseline_pass: set[str]; flaky: set[str]
class InterfaceContract(BaseModel): kind: Literal["function", "method", "cli", "http", "class"]; signature: str; module: str; behaviour: str
class TaskSpec(BaseModel): id: str; archetype: Archetype; title: str; requirements: list[str]; contract: list[InterfaceContract]; acceptance: list[str]; edge_cases: list[str]; out_of_scope: list[str]
class GateResult(BaseModel): gate: GateName; passed: bool; details: dict; log_path: str
class TaskEvidence(BaseModel): spec: TaskSpec; repo: RepoSnapshot; gates: list[GateResult]; harbor: HarborRunSummary; cost: CostSummary
```

---

## 6. Variation strategy (20% of the score)

**Behaviour archetypes.** Each task is assigned one archetype, and a suite spreads across them:

| Archetype | Example in a shopping-cart repo |
|---|---|
| Validation / business rule | Discount codes need a minimum spend and an eligible category |
| State machine / lifecycle | Orders gain a "partially refunded" state with legal transitions |
| Query / filter / aggregation | Report revenue by category over a date range |
| Configuration / policy | A pluggable rounding policy per currency |
| Interaction between components | A loyalty-points earn rate that depends on the applied discount |
| Error handling / robustness | Reject malformed codes with typed errors and messages |
| Interface extension | A new CLI subcommand or API endpoint exposing an existing capability |

**Measuring variation, so the claim is backed by numbers:**
1. **Cross-task discrimination matrix.** Run task *i*'s feature tests against task *j*'s reference, for every pair. Off-diagonal cells should FAIL, which shows the tasks check different behaviour.
2. **Footprint overlap.** Jaccard similarity of the files and symbols touched by each reference patch.
3. **Archetype and extension-point coverage** across the suite.
4. **Spec similarity** via an LLM judge, used only to flag near-duplicates, and reported as such.

---

## 7. Proposed directory layout

```
codeforge/
├── pyproject.toml              # uv-managed, Python ≥3.12
├── .env.example                # model keys etc.; .env is gitignored
├── codeforge.example.yaml      # per-repo recipe overrides
├── src/codeforge/
│   ├── cli.py                  # `codeforge run|analyze|synthesize|validate|package|report`
│   ├── config.py               # pydantic-settings
│   ├── models.py               # shared Pydantic schemas
│   ├── logging.py
│   ├── repo/       (intake.py, fingerprint.py)
│   ├── env/        (builder.py, recipes/, sandbox.py, parsers/junit.py)
│   ├── analysis/   (symbols.py, repomap.py, tests_inventory.py, extension_points.py)
│   ├── synthesis/  (llm.py, planner.py, spec.py, tests.py, reference.py, mutants.py, prompts/)
│   ├── validation/ (gates.py, mutation.py, repair.py)
│   ├── harbor/     (packager.py, templates/, runner.py)
│   └── reporting/  (evidence.py, variation.py, html.py)
├── tests/                      # CodeForge's own tests (unit + integration on a fixture repo)
│   └── fixtures/tiny_cart/     # small purpose-built repo for offline tests (NOT the supplied repo)
├── runs/                       # per-run artifacts (gitignored, sample run committed for judges)
├── tasks/                      # emitted Harbor packages (sample set committed)
└── docs/
```

---

## 8. Open questions (blocking or shaping the design)

1. **The supplied repository** and its language, framework and test runner. Not received yet. Everything in B and C is generic until then.
2. **The exact task interface** Innodata expects. Is it plain Harbor, or Harbor plus their own conventions (naming, required metadata, a pinned Harbor version)?
3. **The model and credits** available during the build phase. This decides the LiteLLM provider and the cost budget.
4. **Rules on manual edits** to generated outputs. The FAQ asks the question but the page doesn't show the answer. We design for zero manual edits either way.
5. **Network policy** inside task containers, and whether `harbor run` is used for judging.
