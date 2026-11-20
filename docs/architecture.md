# CodeForge AI: architecture

Status: **implemented** (CodeForge 0.1.0). It is verified against the installed Harbor
0.26.0 and Docker 29 on Windows 11, using the bundled sample repository. That repository
is a development sample, **not** the Innodata-supplied repository, which had not been
provided at the time of writing.

## 1. The strategy

> **Contract-first feature synthesis with adversarial validation.**
> Pick an extension point and a behaviour archetype. Write a spec whose interface contract
> names exactly what hidden tests may touch. Generate the tests and the reference
> implementation independently, from the spec only. Then accept the task only if executed
> evidence shows the tests fail without the feature, pass with it, keep existing tests
> green, and catch plausible wrong implementations.

## 2. Pipeline

```
           ┌──────────────┐   pinned SHA, git archive snapshot (no .git)
 repo ────▶│ Repository   │── repository/git_manager.py
           └──────┬───────┘
                  ▼
           ┌──────────────┐   languages, manifests, framework, test runner, profile
           │ Intelligence │── repository/{language_detector, dependency_analyzer, parser,
           │              │   symbol_extractor, repo_mapper, profiles, repository_profiler}
           └──────┬───────┘
                  ▼
           ┌──────────────┐   pinned base image digest, task image, validation image,
           │ Environment  │   baseline ×3, flaky detection, shortcut scan
           │              │── environment/{profile_builder, docker_builder, environment_validator}
           └──────┬───────┘
                  ▼
           ┌──────────────┐   7 archetypes, existing-name conflicts, novelty vs registry
           │ Discovery    │── discovery/{feature_discovery, novelty_checker, feature_ranker}
           └──────┬───────┘
                  ▼
           ┌──────────────┐   spec ─▶ hidden tests ‖ reference (separate calls)
           │ Generation   │── generation/{task_generator, test_generator, reference_generator,
           │              │   patch_generator, mutant_generator, context}
           └──────┬───────┘
                  ▼
           ┌──────────────┐   RED, GREEN, regression, stability, coverage, independence
           │ Validation   │── validation/{engine, test_runner, independence_checker}
           │  ⟲ repair    │   repair loop: traceback diagnosis picks tests or reference
           │              │── validation/{mutation_validator} + semantic mutants
           └──────┬───────┘
                  ▼
           ┌──────────────┐   harbor init ▶ fill ▶ lint ▶ oracle (1.0) ▶ nop (0.0) ▶ leakage
           │ Harbor       │── harbor/{task_builder, test_packager, solution_packager,
           │              │   metadata_builder, harbor_validator, templates/grade.py}
           └──────┬───────┘
                  ▼
           ┌──────────────┐   summary.json, report.html, discrimination matrix, events
           │ Reporting    │── reporting/{evidence_manager, variation, html_report}
           └──────────────┘
```

The orchestrator is `pipeline.py`. It emits events, which the CLI logs and the web
dashboard (`web/server.py` + `web/static/`) streams. All data contracts are Pydantic models
in `schemas/`.

## 3. Key design decisions

### Execution isolation
Generated and target code runs only in `DockerSandbox.run_script`: `--network none`,
memory, CPU and PID limits, `--cap-drop ALL`, `no-new-privileges`, tmpfs `/tmp`, no bind
mounts (files move with `docker cp`), and the container is always removed. Subprocesses take
argument lists only; there is no shell string interpolation of untrusted values.

### Two images per repository
- **Task image** (`codeforge-env/<repo>:<sha12>`): exactly what the agent gets. It holds the
  repository and its dependencies, with no tests from CodeForge, no solution and no `.git`.
- **Validation image** (`codeforge-val/...`): the task image plus pinned `coverage`. Only
  CodeForge uses it.

### Harbor package (verified with Harbor 0.26.0)
- `schema_version = "1.4"`. Only fields from `harbor task schema`; provenance lives in
  `[metadata]`.
- `[verifier] environment_mode = "separate"`, so `harbor lint` passes (shared mode
  triggers `shared-verifier`). Top-level `artifacts = [{source = "/app", ...}]` carries the
  agent's source tree into a fresh verifier container built from `tests/Dockerfile`.
- `tests/test.sh` writes `{"reward": 0.0}` first, removes agent-added `conftest.py` and
  `sitecustomize.py`, restores pristine original tests and config, installs the hidden tests,
  runs feature and regression suites with JUnit, and grades with `tests/grade.py`
  (stdlib only).
- `solution/solve.sh` writes the reference files from base64, so the content survives
  quoting and CRLF.
- The reward is 1.0 only if every hidden feature test and every pass-to-pass regression
  test passed.

### Test identity
Test IDs are `classname::name` from JUnit, identical in `adapters/testing/junit.py` and the
shipped `grade.py`. A unit test asserts they match.

### Mutation
`validation/mutation_validator.py` mutates **only the lines the reference added or
changed**, using mutmut-style operator families. It splices mutations into the source by
position, so diffs are minimal. This measures how well the hidden tests pin the *new*
behaviour. LLM semantic mutants add realistic, language-agnostic wrong implementations.

### Repair loop
`pipeline.diagnose_failures` reads JUnit tracebacks:
- Errors in unchanged code or test setup blame the **tests**.
- A crash inside the reference's files blames the **reference**.
- An assertion mismatch is unclear: the reference is regenerated first, then the tests.

The loop is bounded by `max_repair_attempts` (default 2). Every attempt is stored in
`validation.json`.

### Variation
- **Discovery:** archetype coverage, rejection of existing-name conflicts, and a similarity
  check (text 0.45, contract 0.25, same archetype 0.2, modules 0.1) against earlier
  candidates and the per-repository registry of accepted tasks.
- **After generation:** the cross-task discrimination matrix runs task *i*'s tests against
  task *j*'s reference. Off-diagonal cells should fail.

### Reproducibility
- The commit SHA is the primary identity; the sample repository's SHA is deterministic.
- Base images are pinned by digest.
- Every LLM response is cached by a hash of (model, prompts, temperature, seed), so a re-run
  replays the same generation.
- Baseline and stability gates repeat runs.

## 4. Module map

| Requirement area | Module(s) |
|---|---|
| Repository intelligence | `repository/git_manager.py`, `repository_profiler.py`, `language_detector.py`, `dependency_analyzer.py`, `parser.py`, `symbol_extractor.py` |
| Repository mapping | `repository/repo_mapper.py`, `repository/queries/*.scm` |
| Profiles (SWE-smith-style) | `repository/profiles.py`, `adapters/languages/*`, `environment/profile_builder.py` |
| Feature discovery and variation | `discovery/*` |
| Task, test, reference generation | `generation/*`, `prompts/*.txt`, `ai/*` |
| Baseline, negative, positive controls | `environment/environment_validator.py`, `validation/engine.py` |
| Regression protection | `validation/engine.py` (pass-to-pass), `harbor/templates/grade.py` |
| Mutation testing | `validation/mutation_validator.py`, `generation/mutant_generator.py` |
| Test independence | `validation/independence_checker.py` |
| Leakage and anti-shortcut | `validation/leakage_checker.py`, `environment_validator.check_image_for_shortcuts`, `harbor/test_packager.py` |
| Validity score | `validation/validity_scorer.py` |
| Harbor packaging and validation | `harbor/*` |
| Agent benchmarking | `evaluation/agent_runner.py` (`codeforge evaluate`) |
| Reporting and dashboard | `reporting/*`, `web/*` |

## 5. Still missing from Innodata
1. The supplied repository (language, framework, test runner).
2. Any extra conventions on top of Harbor (naming, required metadata, a pinned Harbor version).
3. Model credits for finalists. CodeForge runs free on Gemini's free tier and Ollama, and
   any LiteLLM model id can be passed with `--model`.
