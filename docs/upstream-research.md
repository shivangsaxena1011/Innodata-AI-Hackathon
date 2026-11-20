# Upstream research: source-level integration analysis

This document records what CodeForge AI studied in each upstream project, at which commit,
under which license, and what was adopted. The repositories were shallow-cloned into
`research/upstream/` (excluded from the distribution) and read at these commits:

| Repository | URL | Commit | License |
|---|---|---|---|
| SWE-smith | https://github.com/SWE-bench/SWE-smith | `9b74ac08118a85c39c356802f7961893af73e07f` | MIT |
| SWE-Gym | https://github.com/SWE-Gym/SWE-Gym | `005c2fbeda594d329f53770707b2ae7832aa6ac8` | Apache-2.0 |
| SWE-bench | https://github.com/SWE-bench/SWE-bench | `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e` | MIT |
| Aider | https://github.com/Aider-AI/aider | `5dc9490bb35f9729ef2c95d00a19ccd30c26339c` | Apache-2.0 |
| py-tree-sitter | https://github.com/tree-sitter/py-tree-sitter | `4a8753910f5bbbd4368ad88fe1357a823506aa53` | MIT |
| Harbor | https://github.com/harbor-framework/harbor | `2ea52267e95ed7fb00bb72f0386d9c1289d331ca` (installed CLI 0.26.0) | Apache-2.0 |

The final integration decisions (what was copied, adapted, installed, or used only as an
idea) are in [source-integration-manifest.md](source-integration-manifest.md). Mapping
tables below use the destination names planned during research; the
`source-integration-manifest.md` is authoritative for where things ended up.

---


Both clones were read-only and no code was executed. I opened every file, class and function named below and confirmed it exists at the pinned commit.

## SWE-smith / SWE-Gym — 1. SWE-smith

- **URL:** https://github.com/SWE-bench/SWE-smith | **Commit:** `9b74ac08118a85c39c356802f7961893af73e07f`
- **SPDX:** `MIT` | **License file:** `LICENSE` ("Copyright (c) 2025 John Yang"; `pyproject.toml` declares `license = {file = "LICENSE"}`)

**Important directories:** `swesmith/profiles/` (one profile per repo, plus a registry), `swesmith/build_repo/` (Docker images), `swesmith/bug_gen/` (candidate generation: `procedural/`, `llm/`, `combine/`, `mirror/`, `adapters/`), `swesmith/harness/` (validate, gather, eval, repair), `swesmith/issue_gen/` (problem statements), `configs/` (`install_repo.sh`, `bug_gen/*.yml`, `issue_gen/*.yaml`), `docs/guides/`, `tests/`.

### Key files and names
- `swesmith/profiles/base.py`
  - `RepoProfile` is an `ABC` `@dataclass` with metaclass `SingletonMeta`, so each profile is a singleton. Its fields are `owner`, `repo`, `commit`, `test_cmd`, `exts`, `eval_sets`, `arch`, `org_dh`, `org_gh`, `timeout=90` (seconds, per candidate run) and `timeout_ref=900` (full-suite reference run). It also has `min_testing` (run only the relevant test files) and `min_pregold` (run the reference per instance instead of once per repo).
  - Abstract methods: `log_parser(log) -> dict[str,str]` and the `dockerfile` property.
  - Overridable methods: `_is_test_path` and `get_test_files`. `get_test_cmd` maps the patch's paths to test files by naming heuristics.
  - Infrastructure methods: `image_name` (includes `commit[:8]`), `build_image`, `_prepare_dockerfile` (adds the BuildKit syntax line and `RUN --mount=type=ssh`), `create_mirror`, `clone`, `extract_entities`, `get_container`, `pull_image` and `push_image`.
  - `Registry(UserDict)` provides `register_profile`, `get` and `get_from_inst`. A module-level `registry = Registry()` holds it.
- `swesmith/profiles/__init__.py` eagerly imports all 11 language modules. Each module registers its own subclasses at import time with a loop over `globals()` (see the end of `python.py`).
- `swesmith/profiles/python.py`, `PythonProfile`:
  - Adds `python_version="3.10"` and `install_cmds=["python -m pip install -e ."]`, plus `test_cmd`: conda activate `testbed`, then `pytest --disable-warnings --color=no --tb=no --verbose`.
  - Its `log_parser` matches the regex `^(\S+)(\s+){status}` for each status in swebench `TestStatus`. `get_test_files` splits on `::`. `build_image` writes `setup_env.sh` plus a Dockerfile from swebench `get_dockerfile_env`.
  - Per-repo subclasses override fields; `Apispec8b421526` overrides `install_cmds` and `AutogradAc044f0d` overrides `log_parser`.
  - Other languages: `GoProfile` in `golang.py` has an inline `dockerfile` and `test_cmd="go test -v ./..."`. Java profiles raise `timeout` to 300 or 400.
- `swesmith/profiles/utils.py` holds shared install snippets (`INSTALL_CMAKE`, `INSTALL_BAZEL`, `X11_DEPS`).
- **Environment creation:**
  - `swesmith/build_repo/try_install_py.py`:
    - `main` clones and checks out the commit, then runs `configs/install_repo.sh`. That script tries test-dependency sources in order: `.[test]` extras, then `requirements-test.txt`, then `SWESMITH_PROFILE_INSTALL_CMDS`.
    - It then smoke-tests with `pytest -q --maxfail=1` (when `_pytest_available`) and runs `conda env export` to produce `sweenv_<repo>.yml`.
  - `swesmith/build_repo/create_images.py` provides `build_profile_image` (`create_mirror` → `build_image` → optional push) and `build_all_images` (a ThreadPool that skips images that already exist).
  - `RepoProfile.create_mirror` re-initialises history with `rm -rf .git; git init`, then a single "Initial commit". It also deletes `.github/workflows`.
- **Candidate generation (`bug_gen`):**
  - `procedural/base.py`: `ProceduralModifier` provides `can_change` (tags plus `min_complexity=3`) and an abstract `modify` that returns a `BugRewrite`.
  - `procedural/python/*.py` contains the Python modifiers, for example `OperationFlipOperatorModifier`, `OperationSwapOperandsModifier`, `OperationChangeConstantsModifier`, `ControlIfElseInvertModifier`, `RemoveConditionalModifier`, `RemoveLoopModifier` and `ClassRemoveFuncsModifier`.
  - `procedural/__init__.py` defines `MAP_EXT_TO_MODIFIERS`.
  - `procedural/generate.py` has `main` and `_process_candidate`, with optional `timeout_seconds` and `max_candidates`.
  - `bug_gen/utils.py`: `generate_patch_fast` builds a difflib unified diff without touching git; `apply_code_change` and `get_patch` are also here.
  - `llm/rewrite.py` `main` blanks an entity with `CodeEntity.stub` and asks an LLM to re-implement it; `llm/modify.py` has `gen_bug_from_code_lm`.
  - `mirror/generate.py` (`recover_sweb_inst`) reverts a real PR. `combine/same_file.py` and `combine/same_module.py` merge bugs. `collect_patches.py` `main` writes `<repo>_all_patches.json`.
  - `constants.py` defines `CodeEntity`, `CodeProperty`, `BugRewrite` and `generate_hash`.
- **Validation and filtering (`harness`):**
  - `utils.py` `run_patch_in_container`:
    - Creates a container with `mem_limit="10g"` and checks out the commit.
    - Applies the patch through `_apply_patch`, trying each entry of `GIT_APPLY_CMDS` in turn. A gold patch is applied with `--reverse`, because SWE-smith's patch *is* the bug.
    - Writes an `eval.sh` that wraps `test_cmd` between `: '>>>>> Start Test Output'` and `: '>>>>> End Test Output'` markers.
    - Runs it with swebench `exec_run_with_timeout(container, ..., timeout=timeout)` and appends `TESTS_TIMEOUT` to the log on timeout.
  - `valid.py`:
    - `main` runs the clean reference once per repo (`<repo>.ref`, with `timeout_ref`). A reference timeout skips the whole repo.
    - `run_validation` runs each candidate with `timeout`. Its statuses are `timeout`, `fail`, `0_f2p` and `1+_f2p`. `print_report` summarises them.
  - `grading.py`:
    - `read_test_output` slices the log between the xtrace markers.
    - `get_valid_report` compares the two runs' status maps per test into `FAIL_TO_PASS`, `PASS_TO_PASS`, `FAIL_TO_FAIL` and `PASS_TO_FAIL`, ignoring tests missing from one side.
    - `test_passed` counts PASSED or XFAIL. `test_failed` counts *missing*, FAILED or ERROR.
    - `get_eval_tests_report` and `get_eval_report` build the resolved status through swebench `get_resolution_status`.
  - `gather.py` `process_instance`:
    - Keeps a candidate only if it did not time out and has at least one F2P and at least one P2P test. PR-mirror candidates with 0 P2P are the exception.
    - Commits "Bug Patch", deletes the F2P test files and commits "Remove F2P Tests" on a per-instance branch.
    - At eval time `run_patch_in_container` does `git checkout HEAD~1` to restore those tests, then `git checkout -- <test files>` after applying the model patch.
  - `repair.py` `main` and `_remove_task_instance`: after a gold re-run, flaky F2P/P2P tests are pruned, and the instance is deleted if no F2P test passes any more.
  - **Caveat:** the direction of each label depends only on argument order. `valid.py` passes the bug run as `val_pregold_path`, so broken tests land in `FAIL_TO_PASS` (the same layout as the `tests/test_logs/run_validation` fixture). `gather.py` reads `PASS_TO_FAIL`, and so does `scripts/bug_gen_modal.py`, which passes the arguments in the opposite order. CodeForge should name the runs explicitly (`original`, `reference`) and not use pre/post-gold labels.
- **Issue text generation:**
  - `issue_gen/generate.py` `IssueGen.generate_issue` builds its prompt from a Jinja template and calls litellm with `temperature=0` and `n=n_instructions`. `maybe_shorten` trims any variable longer than `max_var_tokens`.
  - Prompt inputs:
    - the bug patch
    - the failing test output, from `get_test_output`
    - the source of up to five F2P tests (`get_test_functions` → `issue_gen/utils.py` `get_test_function` / `extract_pytest_test`)
    - SWE-bench Verified issues as style demonstrations
  - `configs/issue_gen/ig_v2.yaml` tells the model not to give away the fix, not to say which tests failed and not to suggest test commands.
  - Alternatives: `get_static.py`, `get_from_tests.py` and `get_from_pr.py`.

### Dependency requirements
- `requires-python >=3.10`, and base `dependencies = []`. The extras are:
  - `validate`: ghapi, python-dotenv, rich, swebench, unidiff, tqdm
  - `generate`: adds docker, libcst, astor, jinja2, portkey-ai, `tree-sitter>=0.25` and the language grammars
  - `all`: adds litellm, openai, datasets, modal, sglang and others
- Runtime needs: a Docker daemon with BuildKit, a GitHub token and org for mirrors (`ghapi`), the Docker Hub org `swebench`, and the conda base image from `swebench.harness.dockerfiles`.
- Importing `swesmith.profiles` already pulls in docker, ghapi, dotenv and swebench, and instantiates every profile. Profile methods such as `mirror_url` and `clone` call the GitHub API through `_is_repo_private` and `_mirror_exists`. **CodeForge should not depend on the package.** It should reimplement the small pieces it needs.

### What CodeForge should adapt
| Source file | Original purpose | Functionality selected | CodeForge destination |
|---|---|---|---|
| `swesmith/profiles/base.py` (`RepoProfile`) | Per-repo install/test spec | Pinned `commit`, `test_cmd`, `timeout`/`timeout_ref`, abstract `log_parser`, `image_name` from commit hash. Drop the singleton and the GitHub coupling | `src/codeforge/repository/profiles.py` |
| `swesmith/profiles/base.py` (`Registry`, `get_from_inst`) | Look up a profile by repo or instance | Plain dict registry keyed by repo slug, with explicit registration (no import-time side effects) | `src/codeforge/repository/profiles.py` |
| `swesmith/profiles/base.py` (`_is_test_path`, `get_test_cmd`) | Find test files and narrow the test command | Test-path heuristic; map changed source files to likely test files for `min_testing` | `src/codeforge/repository/profiles.py` |
| `swesmith/profiles/python.py` (`PythonProfile`) | Python defaults and pytest parsing | `python_version`, `install_cmds`, verbose pytest command, per-repo overrides | `src/codeforge/repository/profiles.py` |
| `swesmith/profiles/python.py` (`build_image`), `base.py` (`_prepare_dockerfile`, `create_mirror`) | Generate Dockerfile and `setup_env.sh`; fresh-history mirror | Render the setup script from the profile; build with `--no-cache`, tagged by commit; `git init` single-commit snapshot with CI removed | `src/codeforge/environment/profile_builder.py` |
| `swesmith/build_repo/try_install_py.py` (`main`), `configs/install_repo.sh` | Find a working install for a new repo | Fallback chain (extras → requirements-test → profile cmds); smoke test before accepting the env; freeze env export | `src/codeforge/environment/profile_builder.py` |
| `swesmith/build_repo/create_images.py` (`build_all_images`) | Parallel image builds | Skip existing images, dedupe by image name, collect failures | `src/codeforge/environment/profile_builder.py` |
| `swesmith/harness/utils.py` (`run_patch_in_container`, `_apply_patch`), `constants.py` (`GIT_APPLY_CMDS`) | Apply patch and run tests in container | Clean checkout of touched files; patch-apply fallback; `eval.sh` with markers; hard timeout; memory limit | `src/codeforge/validation/environment_validator.py` |
| `swesmith/harness/grading.py` (`get_valid_report`, `read_test_output`) | Classify per-test transitions | Four-way F2P/P2P/F2F/P2F diff of two status maps (original vs reference) for RED/GREEN/REGRESSION | `src/codeforge/generation/candidate_filter.py` |
| `swesmith/harness/valid.py` (`main`, `run_validation`), `gather.py` (`process_instance`) | Filter candidates | Run the original once per repo, then each candidate; reject on timeout; require ≥1 F2P and ≥1 P2P | `src/codeforge/generation/candidate_filter.py` |
| `swesmith/harness/grading.py` (`test_failed`, `get_eval_tests_report`) | Grade a solution | A missing test counts as failed; split results into success/failure per F2P and P2P | `src/codeforge/validation/environment_validator.py` |
| `swesmith/harness/repair.py` (`main`) | Prune flaky tests after gold re-runs | Re-run the reference N times; drop unstable tests; discard the task if F2P becomes empty | `src/codeforge/validation/reproducibility.py` |
| `swesmith/bug_gen/procedural/base.py` and `procedural/python/*.py`, `bug_gen/utils.py` (`generate_patch_fast`) | Procedural AST bug injection | Apply the operators to the *reference patch's* changed entities to create wrong implementations for MUTATION (hidden tests must catch them); difflib patch generation | `src/codeforge/generation/candidate_filter.py` |
| `swesmith/issue_gen/generate.py`, `configs/issue_gen/ig_v2.yaml` | LLM issue text | Rules: no solution code, no hidden test names. Add a check that rejects specs containing reference-patch lines or hidden test identifiers | `src/codeforge/generation/candidate_filter.py` (spec-leak gate) |

### Copy or idea?
Take the ideas only. Each useful piece is short logic that is easy to rewrite against our own models. `get_valid_report` is about 30 lines, the pytest regex is 1 line, and `GIT_APPLY_CMDS` is 3 strings:
```python
GIT_APPLY_CMDS = [
    "git apply --verbose",
    "git apply --verbose --reject",
    "patch --batch --fuzz=5 -p1 -i",
]
```
If we reuse anything close to verbatim (at most this list or the transition loop), we add a comment `# Adapted from SWE-smith (MIT, (c) 2025 John Yang), commit 9b74ac0` and include the MIT notice in `THIRD_PARTY_NOTICES`.

## SWE-smith / SWE-Gym — 2. SWE-Gym

- **URL:** https://github.com/SWE-Gym/SWE-Gym | **Commit:** `005c2fbeda594d329f53770707b2ae7832aa6ac8`
- **SPDX:** `Apache-2.0` | **License file:** `LICENSE`. This is the standard Apache 2.0 text with an unfilled `Copyright [yyyy] [name of copyright owner]` placeholder. There is no `NOTICE` file.

**Important directories:** `scripts/moatless-verifier/` (data prep for a verifier/reward model), `scripts/openhands-verifier/` (notebooks for reward-model data and pass@n stats), `scripts/training/openhands/` (torchtune and unsloth training on Modal, plus YAML configs), `scripts/serving/` (SGLang), `scripts/modal_misc/`, `docs/` (`OpenHands.md`, `MoatlessTools.md`), `assets/` (paper PDF).

### Key files and names
- **This repo contains no environment-construction or test-verification harness.**
  - The README says the environment constants live in an external `SWE-Gym/SWE-Bench-Fork`, with prebuilt per-instance images under `xingyaoww/sweb.eval.x86_64.*`.
  - `docs/OpenHands.md` sends rollout and eval to an external OpenHands fork (`scripts/rollout-swe-train-full.sh`, `scripts/eval-swetrain-full-rollout.sh`). Those scripts are not in this clone.
  - Verification is SWE-bench style: the notebook `scripts/openhands-verifier/aggregate_stats_pass_at_n.ipynb` reads `test_result['report']['resolved']` and computes pass@k and best@k.
- `scripts/moatless-verifier/repo.py`:
  - `setup_github_repo`, `setup_swebench_repo` (clones from mirror orgs `swe-train/` or `swe-bench/`, then `checkout_commit` to `base_commit`) and `clean_and_reset_state` (`git clean -fd` + `git reset --hard`).
  - `ExecWrapper` and `apply_patch`: binary-file diffs are excluded with `--exclude`, then `git apply -v` is tried with a fallback to `patch --batch --fuzz=5 -p1`. A partial apply is rolled back by saving the initial `git diff` and re-applying it.
  - The file header says it was modified from moatless-tools and SWE-bench-docker.
- `scripts/moatless-verifier/utils.py`, `prepare_spans.py`, `parse_to_orm_data.py` and `prompts.py` turn trajectories into reward-model data. They are not relevant to the environment.
- **README warning about the git shortcut (quote, 10 words):** "SWE-Gym envs contain a git shortcut similar to SWE-bench #465." The README tells users to run a git cleanup script before use.
  - **The loophole (SWE-bench #465):** the image's repo keeps git state *after* the base commit: remote-tracking refs, other branches, tags, reflog and unreachable objects. An agent can run `git log --all`, `git log --grep=<issue#>`, `git show-ref`/`git checkout <tag>`, `git reflog` or `git fsck --lost-found` to find the real fix commit and copy it. It then passes the hidden tests without solving the task.
  - **Upstream mitigation:** remove the origin, the other branches, future tags and the reflog, then run `git gc --prune=now`. Keep tags dated before the base commit, because some tasks legitimately need them. This shipped in swebench 4.1.0.

### Dependency requirements
There is no `requirements.txt`, `pyproject.toml` or `setup.py`. The scripts assume:
- `modal`
- `torchtune` (pinned to git commits) and `unsloth`
- `sglang[all]==0.3.6`, `transformers`, `peft`
- `datasets`, `pandas`
- `moatless` (Moatless-Agent-Fork) and `openhands` (fork)

None of this is needed by CodeForge.

### What CodeForge should adapt
| Source file | Original purpose | Functionality selected | CodeForge destination |
|---|---|---|---|
| `README.md` (git-shortcut warning → SWE-bench #465) | Warn about reward hacking | History sanitisation plus an assertion: one reachable commit, no remotes, branches, tags, stash or reflog, no unreachable objects (`git fsck --unreachable` empty) | `src/codeforge/validation/environment_validator.py` |
| `scripts/moatless-verifier/repo.py` (`apply_patch`) | Robust patch application | Exclude binary hunks; `git apply` → `patch --fuzz` fallback; roll back a partial apply | `src/codeforge/validation/environment_validator.py` |
| `scripts/moatless-verifier/repo.py` (`clean_and_reset_state`) | Reset the workspace between runs | Reset before every run (use `git clean -fdx` so ignored build artefacts go too) | `src/codeforge/validation/reproducibility.py` |
| `README.md` + `docs/OpenHands.md` (per-instance prebuilt images, pinned env constants) | Reproducible environments | One immutable image per task, tagged by repo+commit, with env constants versioned beside the task | `src/codeforge/environment/profile_builder.py` |
| `scripts/openhands-verifier/aggregate_stats_pass_at_n.ipynb` | pass@k stats from `resolved` | Repeat GREEN and REGRESSION runs k times; the task is accepted only if the result is stable in every run | `src/codeforge/validation/reproducibility.py` |

### Copy or idea?
Idea only. `repo.py` has mixed provenance (moatless-tools and SWE-bench-docker), and copying from Apache-2.0 would bring NOTICE and change-marking duties for very little code. We implement our own git sanitiser and patch applier.

## SWE-smith / SWE-Gym — 3. Anti-shortcut lessons for CodeForge task environments
1. **No future or solution git state.** Build the task repo the way `create_mirror` does: a fresh `git init` with a single commit of the *original* snapshot, no remote, no tags, no stash, reflog expired and `git gc --prune=now`. `environment_validator` should check that `git rev-list --all --count` == 1 and that `git fsck --unreachable` is empty.
2. **Never keep the reference patch or hidden tests in the image history.** SWE-smith's branch layout ("Bug Patch" → "Remove F2P Tests", restored at eval with `HEAD~1`) means `git show HEAD~1` would reveal both unless the harness hides history. Hidden tests should be copied in only at verification time, from outside the agent's container.
3. **Restore every test-controlling file before grading.** SWE-smith only reverts test files (`git checkout -- <test files>`). We also need to restore `conftest.py`, `pytest.ini`, `tox.ini`, `setup.cfg`, `pyproject.toml` `[tool.pytest]`, `sitecustomize.py` and plugin entry points.
4. **Missing, skipped or xfail tests are failures.** SWE-smith's `test_failed` already treats a missing test as failed, but `test_passed` accepts XFAIL. We treat XFAIL, SKIPPED and errors as failures for F2P and P2P.
5. **Do not trust stdout that the code under test controls.** The marker slicing and `^(\S+)\s+PASSED` parsing can be spoofed by printed text. Use `pytest --junitxml` written to a path outside the repo, or random per-run markers.
6. **A timeout is a failure.** Reject the task if the original or reference run times out (the `KEY_TIMED_OUT` handling in `valid.py`/`gather.py`). Keep separate, profile-level timeouts for one test run and for the full suite.
7. **Isolate the verifier.** SWE-smith containers set `mem_limit` but no network mode. Run grading with `--network none` and pinned dependencies so a solution cannot fetch the upstream code.
8. **Specs must not leak.** Following `ig_v2.yaml`: no solution code, no hidden test names or file paths, no "run pytest X". Check this automatically against the reference diff and the hidden test identifiers.
9. **Flaky tests invalidate a task.** Follow `repair.py`: run the reference several times, drop unstable tests and discard the task if no stable F2P test remains.

---


Every path and name below comes from reading the local clones. Harbor runtime behaviour was also checked against the installed Harbor 0.26.0 (`.../uv/tools/harbor/Lib/site-packages/harbor`). Its `lint/` package matches the clone exactly once CRLF is ignored. Other modules (oracle, CLI, jobs) differ a little, so for runtime facts the installed 0.26.0 code is the source.

## SWE-bench / Harbor — 1. SWE-bench

- URL: https://github.com/SWE-bench/SWE-bench. Commit `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e` (2026-09-02). SPDX: `MIT`. Package version `swebench/__init__.py` reports `5.0.2`.
- **Version skew:** v5 removed the v4 API: `swebench/harness/test_spec/`, `MAP_REPO_VERSION_TO_SPECS`, `MAP_REPO_TO_PARSER`, `KEY_INSTANCE_ID` and `get_test_directives`. Each instance now carries its own `eval_script`, `log_parser` (a name), `eval_type` and `image`. Harbor's swebench adapter still imports the v4 API (its template pins `swebench==4.0.3`).
- **No base/env/instance tiers any more.** There is only one per-instance image, built from a pre-generated Dockerfile. `swebench/image_builder/__init__.py` still lists `build_base_images` and `build_env_images` in `__all__`, but neither is defined anywhere.

Important directories: `swebench/harness/` (run, grade, docker utils), `swebench/harness/log_parsers/` (python, javascript, go, java, c, php, ruby, rust), `swebench/harness/constants/`, `swebench/image_builder/`, `swebench/task/` (on-disk task repo format: `task.yaml`, `tests.json`, `gold.patch`, `test.patch`, `eval.sh`, `problem_statement.md`, `Dockerfile`).

Key files and functions:
- **Patch application:** `swebench/harness/run_evaluation.py` has `GIT_APPLY_CMDS = ["git apply --verbose", "git apply --verbose --3way", "git apply --verbose --reject", "patch --batch --forward --fuzz=5 -p1 -i"]`. `run_instance()` copies the patch to `/tmp/patch.diff` (`CONTAINER_PATCH_FILE`) and tries each command as `root` in `/testbed`. Between attempts it runs `git checkout -- . ; git clean -fd`. If every command fails, it runs `git apply --check --reverse` to detect a patch that is already applied, then raises `EvaluationError` with `>>>>> Patch Apply Failed`.
- **Docker image building:** `swebench/image_builder/image_spec.py` has `ImageSpec` (name `sweb.eval.{x86_64|arm64}.{instance_id}:{tag}`; for remote images `__` becomes `_1776_`) and `make_image_spec()`. `swebench/image_builder/docker_build.py` has `build_image()` (runs `docker buildx build --platform --tag --file --load`, logging to `logs/image_builder/<name>/build_image.log`), `build_instance_image()` (skips the build if the image exists) and `build_instance_images()` (thread pool). Constants live in `swebench/image_builder/constants/__init__.py`: `CONTAINER_USER="root"`, `CONTAINER_WORKDIR="/testbed"`.
- **Container and test execution:** `run_evaluation.py` has `create_container()` (`tail -f /dev/null`, `cap_add=["SYS_ADMIN"]`; pulls the image if it is missing) and `run_instance()` (writes `eval.sh`, copies it to `/eval.sh`, runs `/bin/bash /eval.sh`). `swebench/harness/docker_utils.py` has `copy_to_container()` (tar plus `put_archive`), `exec_run_with_timeout()` (a thread; on timeout it sends `kill -TERM` to the exec PID; output is decoded with `errors="replace"`) and `cleanup_container()`. `swebench/harness/utils.py` has `make_test_spec()`, `parse_eval_script()` and `record_test_exit_code()`, which echoes `>>>>> Test Exit Code: $?` after the end marker. `swebench/types.py` has `TestSpec.eval_script`, which prepends `#!/bin/bash` and `set -uxo pipefail`.
- **Log parsing:** the parser map is `PARSER_REGISTRY` in `swebench/harness/log_parsers/__init__.py`, a dict from parser name to function. The instance field `log_parser` selects the entry, for example `"parse_log_pytest"`. `log_parsers/python.py` has `parse_log_pytest` (lines that start with a `TestStatus` value, taking `split()[1]` as the test id; it expects `pytest -rA`), `parse_log_pytest_options`, `parse_log_pytest_v2` and per-repo variants (django, sympy, matplotlib and others).
- **Grading:** `swebench/harness/grading.py` has these pieces:
  - `get_logs_eval(test_spec, log_fp)` rejects the run on bad markers, slices the log between `>>>>> Start Test Output` and `>>>>> End Test Output`, and falls back to the whole log. It treats the run as invalid when nothing parses and `SUITE_RAN` does not match, and when the exit code is non-zero but no test is marked failed.
  - `test_passed` accepts PASSED or XFAIL. `test_maintained` adds SKIPPED, as P2P semantics. `test_failed` counts a missing test, FAILED, ERROR or SKIPPED.
  - `_resolve_case()` prefix-matches truncated parametrised test ids.
  - `get_eval_tests_report(eval_status_map, gold_results, calculate_to_fail=False, eval_type=EvalType.PASS_AND_FAIL)` returns `{FAIL_TO_PASS|PASS_TO_PASS|FAIL_TO_FAIL|PASS_TO_FAIL: {"success": [...], "failure": [...]}}`.
  - `compute_fail_to_pass` and `compute_pass_to_pass` return 1 when the list is empty. `get_resolution_status` returns `RESOLVED_FULL` only when both are 1.
  - `get_eval_report()` returns `{iid: {patch_is_None, patch_exists, patch_successfully_applied, resolved, infra_failure, tests_status}}`.
- **Constants:** `swebench/harness/constants/__init__.py` has the `TestStatus` values FAILED, PASSED, SKIPPED, ERROR and XFAIL, plus `ResolvedStatus`, `EvalType` (`pass_and_fail` / `fail_only`), the log markers, `LOG_REPORT="report.json"` and `LOG_TEST_OUTPUT="test_output.txt"`. Logs are written to `logs/evaluation/<run_id>/<model>/<iid>/`.

| Source file | Original purpose | Functionality selected | CodeForge destination |
|---|---|---|---|
| `swebench/harness/run_evaluation.py` (`GIT_APPLY_CMDS`, `run_instance`) | Apply a model patch in the container | 4-step apply fallback, reset between attempts, reverse-check for an already-applied patch | `src/codeforge/evaluation/patch_evaluator.py` |
| `swebench/harness/run_evaluation.py` (`create_container`); `swebench/harness/docker_utils.py` (`copy_to_container`, `exec_run_with_timeout`, `cleanup_container`) | Container lifecycle | tar upload, timed exec with kill, guaranteed cleanup | `src/codeforge/evaluation/patch_evaluator.py` |
| `swebench/image_builder/docker_build.py` (`build_image`, `build_instance_image`); `image_spec.py` (`ImageSpec`) | Per-instance buildx image | Deterministic image naming, skip if the image exists, build log file | `src/codeforge/evaluation/patch_evaluator.py` |
| `swebench/harness/utils.py` (`record_test_exit_code`, `parse_eval_script`); `swebench/types.py` (`TestSpec.eval_script`) | Assemble the eval script | Start/End markers plus recorded test exit code | `src/codeforge/harbor/test_script.py` |
| `swebench/harness/log_parsers/python.py` (`parse_log_pytest`, `_is_skip_summary`); `log_parsers/__init__.py` (`PARSER_REGISTRY`) | Map a pytest `-rA` log to `{test_id: status}` | Pytest status-map parser and a registry selected by name | `src/codeforge/evaluation/result_collector.py` |
| `swebench/harness/grading.py` (`get_logs_eval`, `test_passed`, `test_failed`, `test_maintained`, `SUITE_RAN`) | Validate and slice logs | Marker slicing, the "suite never ran" guard, exit-code cross-check | `src/codeforge/evaluation/result_collector.py` |
| `swebench/harness/grading.py` (`get_eval_tests_report`, `compute_pass_to_pass`, `get_resolution_status`, `get_eval_report`) | F2P/P2P grading | F2P = hidden feature tests, P2P = regression tests, FULL only when both reach 1.0 | `src/codeforge/validation/regression_validator.py` |
| `swebench/harness/constants/__init__.py` | Shared enums and markers | `TestStatus`, `ResolvedStatus`, marker strings | `src/codeforge/evaluation/result_collector.py` |

## SWE-bench / Harbor — 2. Harbor

- URL: https://github.com/harbor-framework/harbor. Commit `2ea52267e95ed7fb00bb72f0386d9c1289d331ca` (2026-11-19; `pyproject` reports 0.26.0). SPDX: `Apache-2.0`. Installed CLI: `harbor 0.26.0`.

Important directories: `adapters/swebench/src/swebench_adapter/` and `adapters/swesmith/src/swesmith_adapter/` (each has `task-template/`), `src/harbor/lint/`, `src/harbor/agents/oracle.py`, `src/harbor/verifier/verifier.py`, `src/harbor/trial/` (`trial.py`, `single_step.py`, `artifact_handler.py`), `src/harbor/models/{task,trial,job}/`, `src/harbor/environments/docker/`, `src/harbor/cli/template-task/`, `examples/tasks/`, `docs-mintlify/tasks/`.

**swebench adapter** (`adapter.py`: `SWEBenchAdapter.generate_task`, `HarborTaskPaths`; `utils.py`: `render_literal`, `get_test_commands`, `_extract_patch_paths`, `get_image_names`):
- Output layout: `instruction.md`, `task.toml`, `environment/Dockerfile`, `tests/test.sh`, `tests/config.json` (the raw dataset row), `solution/solve.sh`.
- `render_literal` does plain `{key}` replacement. It fills `{problem_statement}`, `{instance_id}`, `{difficulty}`, `{max_timeout}` (default 3000), `{docker_image}` (`instance_image_key` with arm64 replaced by x86_64), `{patch}` and `{test_commands}`.
- `task.toml`: `schema_version="1.0"`, `[task] name="swe-bench/swebench-verified__{id}"`, `[verifier]`/`[agent]` with `network_mode="public"` and `timeout_sec`, `[environment]` with `build_timeout_sec=1800`, `cpus=1`, `memory_mb=4096`, `storage_mb=10240`. It sets no `environment_mode` and no `agent.user`.
- `Dockerfile`: `FROM {docker_image}`, `WORKDIR /testbed`, `RUN curl ... uv/0.7.13/install.sh | sh`, `mkdir -p /logs`.
- `solve.sh`: `set -euo pipefail`, writes the patch through a `<< '__SOLUTION__'` heredoc to `/testbed/solution_patch.diff`, then `cd /testbed; patch --fuzz=5 -p1 -i`.
- `test.sh`:
  1. The eval body (conda activate, reset the test files touched by `test_patch` with `git checkout <base>`, delete untracked test-patch files, `git apply` the test patch, tee the test output into `$LOG_FILE`, `|| true`, reset again).
  2. A `uv run parser.py` step (PEP 723 deps `swebench==4.0.3`) that wraps the log in Start/End markers and calls `get_logs_eval` and `get_eval_tests_report`. It writes `/logs/verifier/report.json`.
  3. A final `echo 1|0 > /logs/verifier/reward.txt`.

**swesmith adapter** (`adapter.py: _prepare_task_from_template`):
- `copytree` of the template, then `str.replace`. `task.toml` goes through a `toml.loads`/`toml.dumps` round trip, with metadata merged in.
- `Dockerfile`: `FROM {image}`, `RUN git fetch && git checkout {instance_id}`.
- `solve.sh`: `git apply --verbose --reject --reverse` of the bug patch.
- `test.sh`:
  1. `apt-get install`, `curl` uv, then run `{run_command}` (`git checkout {id}; git checkout HEAD~1; <test cmd>`) into `/logs/test_output.log`.
  2. `uv init; uv add pytest==8.4.1 ... swesmith==0.0.6`, then run `pytest --ctrf /logs/verifier/ctrf.json test_state.py`. `test_state.py` asserts `resolved`.
  3. Write `reward.txt`.
- Both adapters use the shared verifier with runtime installs. When I ran `harbor lint` on comparable tasks (`examples/tasks/hello-world`, `deepswe_tomlkit-...`), both reported `[shared-verifier]`.

**Lint** (`src/harbor/lint/models.py`, `task.py`, `compose.py`; CLI in `src/harbor/cli/lint.py`; run as `harbor lint TASK_DIR... [--json] [--select R|ALL] [--extend-select R|ALL] [--ignore R]`):
- **Severity:** there is none. `LintFinding` only has `{rule, path, message, line, column}`. Any selected finding makes the command exit 1. An operational error exits 2.
- **On by default** (`DEFAULT_RULES`): every rule except `root-agent` and `unpinned-image`. Those two run only with `--select`/`--extend-select` (including `ALL`).
- **Config sources:** `[metadata.harbor.lint]` in a parent `dataset.toml`, then in the task's own `task.toml` (`select`, `extend-select`, `ignore`), then the CLI flags.

What each rule checks (heredoc bodies, `#` comments and blank lines are skipped; `\` continuations are joined):
- `invalid-task-config`: malformed TOML or a pydantic `TaskConfig` validation error.
- `unknown-config-field`: an unknown key in `task.toml`, with a "did you mean" suggestion.
- `invalid-task-files`:
  - `task.toml` is missing.
  - `environment/` is missing and no `environment.docker_image` is set.
  - `instruction.md` is missing, or empty after `strip_canary`.
  - No OS-compatible `tests/test.sh`. This check is skipped when a verifier image bundles the tests.
  - A symlink escapes the task or forms a cycle.
  - A `.harborignore` is invalid.
- `unused-harborignore`: a `.harborignore` that sits outside `tests/` or `solution/`.
- `shared-verifier` (default): resolved verifier mode is `shared`, which is also the default when both `verifier.environment_mode` and `[verifier.environment]` are omitted. Fix: `environment_mode = "separate"`.
- `root-agent` (off by default): `agent.user` (or a step override) is omitted, `root`, or `0`.
- `overlapping-artifacts` / `artifact-log-overlap`: artifact entries collide with each other, or (for separate verifiers) overlap `/logs/verifier` or `/logs/agent`.
- `compose-*` (5 rules): only apply to `environment/` or `tests/docker-compose.yaml` (privileged mode, `cap_add`, writable, external or symlink bind mounts).
- `unpinned-image` (off by default): a `FROM` line or `docker_image` not pinned to `@sha256:<64 hex>`. `scratch` and values containing `$` are exempt.
- `unpinned-python-dependency` (default):
  - Applies to `RUN` lines in Linux Dockerfiles, to `test.sh` and to `solve.sh`.
  - Inspected commands: `pip|pip3 install`, `python -m pip install`, `uv pip install`, `uv tool install`, `uvx --with`.
  - Each package needs `==`/`===` without `*`; a VCS URL needs a 40-hex commit or `#sha256=`.
  - Exempt: `-r` / `-c`, local paths (`.`, `/`, `file:`), wheels and sdists, `pip install -U pip`.
  - `uv add`, `poetry` and `conda` are not inspected.
- `verifier-runtime-install` (default, only for the `test.sh` of a separate verifier): installing `pytest` or `pytest-json-ctrf` without `--offline` or `--no-index`.
- `verifier-network-download` (default, only for the `test.sh` of a separate verifier):
  - `git clone` of an external host.
  - `curl` or `wget` to an external host (one with a dot in it, not `127.*`, not `*.localhost`) that is piped to `sh` or `bash`, or that saves output (`-o`, `-O`, `>`, or any `wget`).
  - Exempt: `--spider`, `-qO-`, and output to `-` or `/dev/null`.
- `agent-image-test-leak` (default): `COPY`/`ADD` in `environment/Dockerfile` whose source matches `solution/solve.sh`, `tests/test.sh` or `tests/test_*.py`.

**Oracle** (`src/harbor/agents/oracle.py`):
- Uploads the filtered `solution/` directory to `/solution` and resolves `solve.sh` (OS-aware discovery).
- Runs `chmod +x /solution/solve.sh` as `root`, then executes the script directly as `(/solution/solve.sh) > /logs/agent/oracle.txt 2>&1`, with env `DEBIAN_FRONTEND=noninteractive` plus `[solution.env]`. Because it executes directly, the shebang is required.
- **User:** `task.config.agent.user` (`single_step.py` passes it to `with_default_user`). `None` means the image's `USER`, usually root.
- **Working directory:** no `cwd` is passed, so it is `[environment].workdir` if set, otherwise the Dockerfile `WORKDIR`.
- A non-zero exit only writes `agent/exit-code.txt`. Verification still runs.

**Verifier** (`src/harbor/verifier/verifier.py`):
- Deletes stale reward files, uploads `tests/` to `/tests` (skipped when tests are bundled in a verifier image), runs `chmod +x` as root, then runs `(/tests/test.sh) > /logs/verifier/test-stdout.txt 2>&1` as `verifier.user`.
- **The exit code is ignored.**
- `reward.json` takes precedence over `reward.txt`. `reward.txt` must hold a single finite float and becomes `{"reward": v}`. `reward.json` must be a JSON object of finite numbers; **no key is required**. With no reward file the trial fails with `RewardFileNotFoundError`.
- Job metrics: one key gives `{"mean": v}`; several keys give a mean per key. Use `{"reward": ...}` as the primary key; extra keys such as `f2p` or `p2p` are allowed.

**Separate-verifier semantics** (`models/task/verifier_mode.py`, `trial/trial.py::_run_separate_verifier`, `docs-mintlify/tasks/separate-verifier.mdx`):
- Image priority: `[verifier.environment].docker_image`, then `tests/Dockerfile` (tests must be baked in at `/tests`), then `[environment].docker_image`, then `environment/Dockerfile` (`tests/` is uploaded).
- **The agent's filesystem changes are not inherited.** Only `/logs/artifacts/` and the declared `artifacts` are copied in. A directory artifact is emptied and then replaced (`artifact_handler.py`: `empty_dirs` + `upload_dir`) after tar `data`-filter sanitisation.

**Running one task with the oracle:**
- `harbor run -p <task_dir> -a oracle -e docker` (alias of `harbor job start`), or `harbor trial start -p <task_dir> -a oracle` (writes to `./trials/<trial_name>/`).
- `-e docker` is the default environment. The cloud is only used with `--launch` (Hub) or `--server`, and `--upload` publishes results. There is no dedicated "local only" flag. Set `HARBOR_TELEMETRY=0` to stop PostHog telemetry.

**Results on disk:**
- Layout: `jobs/<job_name>/`, where the default `job_name` is `%Y-%m-%d__%H-%M-%S` and `-o` changes the root. It contains `config.json`, `lock.json`, `result.json` (`JobResult`), `job.log` and `<trial_name>/`. The trial name is `<task_name[:32]>__<7-char shortuuid>`.
- A trial directory holds `result.json` (`TrialResult`; its docstring says "results.json", but the code writes `result.json`), `config.json`, `trial.log`, `exception.txt`, `agent/oracle.txt`, `verifier/{reward.txt|reward.json,test-stdout.txt}` and `artifacts/`.
- `TrialResult` fields: `task_name`, `trial_name`, `verifier_result.rewards`, `exception_info`, `verifier_environment_mode`, `agent_execution` and `verifier` timings, and the `reward_valid` property.
- `JobResult` holds `stats.evals["oracle__<dataset>"].metrics` and `reward_stats`, plus `trial_results`.

Reading the reward programmatically:

```python
from harbor.models.trial.result import TrialResult
r = TrialResult.model_validate_json(Path(trial_dir, "result.json").read_text())
reward = (r.verifier_result.rewards or {}).get("reward") if r.verifier_result else None
```

**Windows host** (`environments/docker/docker_unix.py::upload_dir`, `docker.py`):
- On `sys.platform == "win32"`, after every `upload_dir` (`/solution`, `/tests` and directory artifacts) Harbor runs `docker compose exec main bash -c "find <dir> ( -name '*.sh' -o '*.py' -o '*.ps1' -o '*.cmd' -o '*.bat' ) -exec sed -i 's/\r$//'"` with `check=False`.
- Consequences:
  - `.patch`, `.diff`, `.json`, `.toml` and data files are **not** normalised.
  - `upload_file` gets no fix.
  - The build context (Dockerfile `COPY`) gets no fix.
  - Images without `bash` fail silently.
  - CR is also stripped from `.py`/`.sh` files inside an uploaded `/testbed` artifact.
- Host paths are passed as absolute Windows paths (`_compose_host_path`), and Docker Desktop accepts them.
- `os = "windows"` tasks require Windows-container mode. Linux tasks run normally.
- The local clone itself was checked out with CRLF (global `core.autocrlf=true`).
- Python `Path.write_text()` writes `\r\n` on Windows.

| Source file | Original purpose | Functionality selected | CodeForge destination |
|---|---|---|---|
| `adapters/swebench/src/swebench_adapter/adapter.py` (`HarborTaskPaths`, `generate_task`); `utils.py` (`render_literal`) | Dataset row to Harbor task dir | Directory layout, `{key}` templating, `chmod 0o755`, `tests/config.json` metadata | `src/codeforge/harbor/task_writer.py` |
| `adapters/swebench/src/swebench_adapter/utils.py` (`get_test_commands`, `_extract_patch_paths`) | Build the `test.sh` eval body | Reset/remove test-patch files, apply hidden tests, tee log, restore | `src/codeforge/harbor/test_script.py` |
| `adapters/swebench/.../task-template/solution/solve.sh`; `adapters/swesmith/.../solve.sh` | Oracle patch application | Quoted heredoc patch (`'__SOLUTION__'`) plus `patch`/`git apply` | `src/codeforge/harbor/solution_script.py` |
| `adapters/swesmith/.../tests/test_state.py`, `test.sh` | Grade inside the verifier and write the reward | Parse log, F2P/P2P report, then `reward.txt` | `src/codeforge/harbor/test_script.py` |
| `src/harbor/lint/models.py`, `task.py`, `compose.py`; `cli/lint.py` | Static task checks | Run `harbor lint --json` as a gate; mirror the pin, download and leak checks | `src/codeforge/harbor/lint_gate.py` |
| `src/harbor/agents/oracle.py`; `verifier/verifier.py` | Oracle run and reward parsing | `/solution` and `/tests` paths, user, reward.txt/json contract | `src/codeforge/harbor/oracle_runner.py` |
| `src/harbor/models/trial/result.py`, `models/job/result.py`, `models/trial/paths.py` | Result schemas and paths | Parse `jobs/<job>/<trial>/result.json` for rewards and exceptions | `src/codeforge/evaluation/result_collector.py` |
| `src/harbor/environments/docker/docker_unix.py` (`upload_dir`) | Windows CRLF fix | Write all task files with LF ourselves | `src/codeforge/harbor/task_writer.py` |

### Packaging rules CodeForge must follow (lint clean under defaults, oracle reward 1)

1. **Task tree:** `task.toml`, a non-empty `instruction.md`, `environment/Dockerfile`, `solution/solve.sh` (shebang `#!/bin/bash`), and `tests/test.sh` plus the hidden test files. Add nothing else (`.harborignore` only inside `tests/` or `solution/`) and no symlinks.
2. **`task.toml`:**
   - Use only known fields. Put `artifacts` at the TOML top level, before any `[section]`.
   - Set `[verifier] environment_mode = "separate"`. Without it, `shared-verifier` fires.
   - Declare the repo as an artifact so the verifier sees the agent's or oracle's edits: `artifacts = [{ source = "/testbed", exclude = ["__pycache__", ".pytest_cache"] }]`. Keep `.git`. It must not overlap `/logs/agent` or `/logs/verifier`.
   - Set `[agent] user = "<non-root>"` so that `--select ALL` also passes `root-agent`. The user must exist and own `/testbed`.
3. **`environment/Dockerfile`:**
   - Pin `FROM` with `@sha256:` (needed for `unpinned-image` under `ALL`).
   - Every `pip`/`uv pip` install needs `==` pins or `-r requirements.txt`/`-c`.
   - Bake `pytest==X` and `pytest-json-ctrf==Y` into this image, because a separate verifier without `tests/Dockerfile` reuses it.
   - Never `COPY` `tests/` or `solution/` into it (`agent-image-test-leak`; the build context is `environment/`).
   - Clone or `git archive` the repo at `base_commit` inside the image rather than copying a Windows working tree.
4. **`tests/test.sh`:**
   - No `pip`/`uv pip`/`uvx` install of pytest, no external `curl`/`wget`/`git clone` (the `verifier-*` rules).
   - Copy `/tests/<hidden tests>` into the repo, run `pytest -rA` with the F2P and P2P ids, and slice the log between the SWE-bench markers.
   - Always write `/logs/verifier/reward.json`, for example `{"reward": 1.0, "f2p": 1.0, "p2p": 1.0}`, or `reward.txt`. The exit code is ignored.
5. **`solution/solve.sh`:** `cd /testbed` and apply the reference patch, either from a quoted heredoc (lint skips heredoc bodies) or from `/solution/ref.patch` with `git apply --whitespace=nowarn`. The script must be idempotent and must not install unpinned packages.
6. **Windows:** write every generated file as bytes or with `newline="\n"`, especially `.patch`, `.diff`, Dockerfiles and JSON (Harbor only fixes `.sh`/`.py`/`.ps1`/`.cmd`/`.bat` after upload). Do not rely on `chmod` (Harbor runs `chmod +x` only on the entry `.sh`; call helper scripts with `bash x.sh`).
7. **Gate:** `harbor lint <task> --json` must return `[]` (try it with `--select ALL` too). Then `HARBOR_TELEMETRY=0 harbor run -p <task> -a oracle -e docker -o <jobs> --job-name <id>` must give `verifier_result.rewards["reward"] == 1` in `<jobs>/<id>/<trial>/result.json` with `exception_info == null`. Optionally, a no-op run (`-a nop`) should give reward 0, which proves the F2P tests fail before the patch.

---


Scope: source-level study of Aider's ranked repo map and the py-tree-sitter 0.26.1 query API, plus
licence review of the `tags.scm` query files CodeForge wants to vendor.

Everything marked "verified" was run in the CodeForge venv (`uv run python`, tree-sitter 0.26.1,
tree-sitter-python 0.25.0, tree-sitter-javascript 0.25.0, networkx 3.7 at research time; CodeForge later replaced networkx with a built-in PageRank). The test scripts are in
research scratch scripts (not distributed)
(`probe_api.py`, `verify_tags.py`, `compare_and_snippet.py`, `upstream_matches.py`).

Vendored, verified queries and their licence texts are in
`src/codeforge/repository/queries/` (licence texts in `licenses/`):
`python-tags.scm`, `javascript-tags.scm`, `LICENSE-tree-sitter-python`, `LICENSE-tree-sitter-javascript`.

---

## Aider / tree-sitter — 1. Aider

- URL: https://github.com/Aider-AI/aider
- Commit: `5dc9490bb35f9729ef2c95d00a19ccd30c26339c` (2026-05-22, shallow clone)
- SPDX licence: `Apache-2.0` (`LICENSE.txt`). There is no `NOTICE` file at this commit.
- Aider's own pins: `tree-sitter==0.25.2` (py>=3.10), `tree-sitter-language-pack==0.13.0`,
  `grep-ast==0.9.0`, `networkx==3.4.2`, `diskcache==5.6.3`.

### 1.1 Key files and functions

| File | Function / item | Role |
|---|---|---|
| `aider/repomap.py` | `Tag = namedtuple("Tag", "rel_fname fname line name kind")` | One def/ref occurrence. `line` is 0-based. `kind` is `"def"` or `"ref"`. |
| `aider/repomap.py` | `RepoMap.get_tags_raw` | Parse one file, run its `<lang>-tags.scm`, and yield `Tag`s. |
| `aider/repomap.py` | `RepoMap._run_captures` | Compatibility shim: `query.captures(node)` (0.23) vs `QueryCursor(query).captures(node)` (0.24+). |
| `aider/repomap.py` | `RepoMap.get_tags`, `get_mtime`, `load_tags_cache`, `tags_cache_error` | Persistent tag cache keyed by file path and validated by mtime. |
| `aider/repomap.py` | `RepoMap.get_ranked_tags` | Builds the reference graph, runs personalised PageRank, and distributes rank onto definitions. |
| `aider/repomap.py` | `RepoMap.get_ranked_tags_map` / `_uncached` | In-memory map cache, then a binary search for the largest prefix of ranked tags that fits the token budget. |
| `aider/repomap.py` | `RepoMap.to_tree`, `render_tree` | Renders the chosen tags per file with `grep_ast.TreeContext`. |
| `aider/repomap.py` | `RepoMap.token_count` | Sampled token estimate for large texts. |
| `aider/repomap.py` | `get_repo_map` | Picks the budget: expands to `map_tokens * 8` when no files are in chat. |
| `aider/repomap.py` | `get_scm_fname` | Finds `queries/<pack>/<lang>-tags.scm` with `importlib.resources`. |
| `aider/special.py` | `filter_important_files` | Root README, `.gitignore`, CONTRIBUTING, `.github/workflows/*.yml` and similar files, prepended to the map. |
| `aider/coders/base_coder.py` | `get_ident_mentions`, `get_file_mentions`, `get_ident_filename_matches`, `get_repo_map` | Derive `mentioned_idents` and `mentioned_fnames` from the current user message, plus fallback calls. |
| `aider/queries/tree-sitter-language-pack/*-tags.scm` | Query files | Used when `grep_ast.tsl.USING_TSL_PACK` is true (current default). |
| `aider/queries/tree-sitter-languages/*-tags.scm` | Query files | Legacy fallback for the older `tree-sitter-languages` wheel. |
| `aider/website/docs/repomap.md` | Docs | High-level description: file graph, ranking, and a token budget (`--map-tokens`, default 1k). |

### 1.2 The algorithm (precise)

#### A. Tag extraction (`get_tags_raw`)
1. `lang = filename_to_lang(fname)`, then get the parser and language from `grep_ast.tsl`, and load the `<lang>-tags.scm` text.
2. Parse `bytes(code, "utf-8")` and run `QueryCursor(Query(language, scm)).captures(root)`, which returns `dict[capture_name, list[Node]]`.
3. Each node captured as `name.definition.*` becomes `Tag(kind="def")`, and each `name.reference.*` becomes `Tag(kind="ref")`. All other captures (`definition.*`, `reference.*`, `doc`) are ignored. `name = node.text`, `line = node.start_point[0]` (0-based).
4. Backfill: if a file produced defs but **no** refs (for example C++ tags files that only define), Aider uses the Pygments lexer for the file and emits every `Token.Name` token as a `ref` with `line=-1`.
5. **Quirk, do not copy:** the loop at repomap.py lines 306-310 has an indentation bug. `captures_by_tag[tag].append(node)` and `matches.append((node, tag))` run once more *after* the inner loop, so in the TSL-pack path the **last node of every capture name is emitted twice**. In the legacy path, only the **last** node per capture name is kept. Verified: for `def a/def b`, the TSL path yields `['a','b','b']`.

#### B. Caching
- **Tag cache:** `diskcache.Cache(<root>/.aider.tags.cache.v{3|4})`. v4 is used when the TSL pack is in use. Key = absolute filename. Value = `{"mtime": os.path.getmtime(fname), "data": [Tag,...]}`. It is a hit only if the stored mtime equals the current one exactly. On a SQLite error the cache directory is deleted and recreated. If that fails too, the cache falls back to an in-memory `dict`.
- **Map cache (in memory):** key = `(sorted chat_fnames, sorted other_fnames, max_map_tokens)`. In `refresh="auto"` mode the key also includes `sorted mentioned_fnames` and `sorted mentioned_idents`. Refresh modes:
  - `always`: never use the cache.
  - `files`: always use the cache.
  - `auto`: use the cache only if the previous map took more than 1.0 s to build.
  - `manual`: return `last_map`.
- **Render caches:** `tree_cache[(rel_fname, tuple(sorted(lois)), mtime)]` holds the rendered text. `tree_context_cache[rel_fname] = {"context": TreeContext, "mtime": mtime}` holds the parsed context, rebuilt when the mtime changes.

#### C. Inputs to the ranking
- `chat_fnames`: absolute paths of files in the chat, plus read-only repo files. `other_fnames`: all other repo files.
- `mentioned_idents = set(re.split(r"\W+", current_message_text))`, i.e. every word of the current user message.
- `mentioned_fnames` comes from two sources:
  - Repo-relative paths, or distinctive basenames (containing `/ . _ -`), that appear as words in the message.
  - Any file whose lowercased stem (5 or more characters) equals a lowercased mentioned word (5 or more characters).

#### D. Graph construction (`get_ranked_tags`)
Data gathered over `fnames = sorted(chat ∪ other)`:
- `defines[ident]`: the **set** of rel files that define `ident`.
- `references[ident]`: a **list** of rel files with one entry per reference occurrence, so it keeps the counts.
- `definitions[(rel_file, ident)]`: the set of `Tag`s.
- If no references exist anywhere, then `references = {k: list(v) for k, v in defines.items()}`.
- `idents = defines.keys() ∩ references.keys()`.

Graph `G = networkx.MultiDiGraph()`:
- **Nodes** are relative file paths. They are created implicitly by `add_edge`, so files with no def/ref edges are not in the graph.
- **Self-edges:** for every ident that is defined but never referenced, add `definer -> definer` with `weight=0.1`, `ident=ident`.
- **Reference edges:** for every `ident` in `idents`, start with `mul = 1.0`, then apply:

  | Condition | Multiplier |
  |---|---|
  | `ident in mentioned_idents` | ×10 |
  | (`is_snake` or `is_kebab` or `is_camel`) and `len(ident) >= 8` | ×10 ("long, specific names") |
  | `ident.startswith("_")` | ×0.1 (private names) |
  | `len(defines[ident]) > 5` (defined in more than 5 files) | ×0.1 (generic names) |
  | per edge: referencer is a chat file | ×50 |

  Definitions used above:
  - `is_snake = "_" in ident and any(c.isalpha())`
  - `is_kebab = "-" in ident and any(c.isalpha())`
  - `is_camel = any(c.isupper()) and any(c.islower())`

  For each `(referencer, num_refs)` in `Counter(references[ident])` and each `definer` in `defines[ident]`, add the edge `referencer -> definer` with `weight = mul * (50 if referencer in chat_rel_fnames else 1) * sqrt(num_refs)` and `ident=ident`. Self-references (referencer == definer) are **kept**. Parallel edges, one per ident, are summed by networkx when it builds the sparse matrix.

#### E. Personalisation vector
- `personalize = 100 / len(fnames)`. Every file starts at `current_pers = 0`, and then:
  - In chat: `+= personalize`.
  - `rel_fname in mentioned_fnames`: `current_pers = max(current_pers, personalize)`, so the two do not double-count.
  - Any of the path parts, the basename, or the stem is in `mentioned_idents`: `+= personalize`, once.
  - Only files with `current_pers > 0` go into the dict.
- `nx.pagerank(G, weight="weight", personalization=pers, dangling=pers)` with the default `alpha=0.85`, `max_iter=100`, `tol=1e-6`. networkx normalises `pers` to sum 1, and nodes missing from it get 0. So the teleport and dangling mass goes **only** to chat, mentioned, or ident-matching files, in a 1:2 ratio for files that hit two criteria. The `100/N` constant cancels out.
- If `pers` is empty, Aider runs plain PageRank (uniform teleport). On `ZeroDivisionError` (no personalised node is in `G`, Issue #1536) it retries without personalisation. If that also fails, it returns `[]`.

#### F. From file rank to definition rank
For each node `src`, for each out-edge `(src, dst, ident, w)`, add `ranked[src] * w / sum(out_weights(src))` to `ranked_definitions[(dst, ident)]`. Then:
1. Sort `(dst, ident)` by `(rank, (dst, ident))`, descending. Skip `dst` files that are in the chat.
2. Expand each entry to its `Tag` definitions, giving the ordered `ranked_tags`.
3. Append the files that are graph nodes but have no ranked defs, in node-PageRank order, as 1-tuples `(rel_fname,)`.
4. Append any remaining `other_fnames` that are not in the graph.
5. In `_uncached`, prepend the "important" files (`filter_important_files`) that are not already present.

#### G. Token budget (`get_repo_map` + binary search)
- Budget: `max_map_tokens = map_tokens` (default 1024). If **no chat files**, use `min(map_tokens * map_mul_no_files(=8), max_context_window - 4096)`.
- The search runs over `n`, the number of leading `ranked_tags` to render:
  ```
  lo, hi = 0, len(ranked_tags); middle = min(max_map_tokens // 25, len(ranked_tags))
  loop while lo <= hi:
      tree = to_tree(ranked_tags[:middle]); t = token_count(tree)
      err = |t - budget| / budget
      if (t <= budget and t > best_t) or err < 0.15: best = tree; best_t = t; if err < 0.15: break
      if t < budget: lo = middle + 1 else: hi = middle - 1
      middle = (lo + hi) // 2
  ```
  Because of the 15% tolerance, the accepted map can be up to **1.15× the budget**.
- `token_count`: texts under 200 chars are counted exactly. Longer texts are counted on a sample of every `(lines // 100)`-th line, and the count is extrapolated by character ratio.
- `to_tree`: sort the tags, group them by file, and skip chat files. A file with tags prints `rel_fname:` followed by the `TreeContext` render, which uses the lines of interest (the def lines) and shows their enclosing scopes with `⋮...` and `│` markers. A file without tags prints just its name. Every line is truncated to 100 chars.

### 1.3 Mapping to CodeForge

| Source file | Original purpose | Functionality selected | CodeForge destination |
|---|---|---|---|
| `aider/repomap.py` `get_ranked_tags` | Build the def/ref file graph and run personalised PageRank | The graph model (file nodes; referencer→definer edges carrying `ident`), the multipliers (×10 mentioned, ×10 long snake/kebab/camel ≥ 8 chars, ×0.1 `_private`, ×0.1 defined in more than 5 files, ×50 chat referencer, `sqrt(num_refs)`), 0.1 self-edges for unreferenced defs, the personalisation and dangling vector, and rank distribution onto `(file, ident)`. **Re-implement; do not copy the code.** | `src/codeforge/repository/repo_mapper.py` |
| `aider/repomap.py` `get_ranked_tags_map(_uncached)`, `token_count` | Fit the map to a token budget | Binary search over the tag prefix (start at `budget//25`, 15% tolerance), the budget expansion when no files are focused, and a sampled token estimate. CodeForge can count with `tiktoken`, which is already installed. | `src/codeforge/repository/repo_mapper.py` |
| `aider/repomap.py` `to_tree`/`render_tree` | Render the selected defs per file | The output shape (`path:` + def lines with elided scopes, lines capped at 100 chars). `grep_ast` is **not** installed in CodeForge, so write a small renderer using `definition.*` node spans, for example the first line of each def plus its parent class line. | `src/codeforge/repository/repo_mapper.py` |
| `aider/repomap.py` `get_tags`, `load_tags_cache` | Persistent per-file tag cache | Cache keyed by path and validated by mtime. Suggest a key of `(path, mtime_ns, size)` or the git blob SHA. `diskcache` is not installed, so use `sqlite3` or JSON. | `src/codeforge/repository/symbol_extractor.py` |
| `aider/repomap.py` `get_tags_raw` | Captures → `Tag(def/ref)` | The capture-name convention `name.definition.<kind>` / `name.reference.<kind>`, 0-based `line`, and the optional Pygments ref backfill. **Do not replicate the duplicate-last-node loop bug.** | `src/codeforge/repository/symbol_extractor.py` |
| `aider/repomap.py` `_run_captures`, `get_scm_fname` | API shim and query file lookup | For 0.26 only `QueryCursor(query).captures(node)` is needed. Load queries with `importlib.resources.files("codeforge.repository.queries")`. | `src/codeforge/repository/parser.py` |
| `aider/special.py` `filter_important_files` | Always include key root files | Optional: prepend README/config files to the map. | `src/codeforge/repository/repo_mapper.py` |
| `aider/coders/base_coder.py` `get_ident_mentions`, `get_ident_filename_matches` | Derive focus from the user's prompt | `mentioned_idents = re.split(r"\W+", prompt)`; stem-match files (5+ chars). | `src/codeforge/repository/repo_mapper.py` |
| `aider/queries/tree-sitter-language-pack/python-tags.scm` | Python defs/refs | Same patterns as upstream 0.25.0 after the `@name` rename (verified identical). CodeForge vendors it from the **upstream MIT file** instead. | `src/codeforge/repository/queries/python-tags.scm` |
| `aider/queries/tree-sitter-language-pack/javascript-tags.scm` | JS defs/refs | Compiles on 0.25. CodeForge vendors from upstream 0.25.0, which adds the `export ... = value` constant pattern, and fixes the `new_expression` capture. | `src/codeforge/repository/queries/javascript-tags.scm` |
| `aider/queries/tree-sitter-languages/javascript-tags.scm` | Legacy JS query | **Do not use:** `QueryError: Invalid node type at row 27, column 5: function`. The node was renamed `function_expression` in newer grammars. | none |
| `aider/website/docs/repomap.md` | User docs | The concept only (file graph, budget, `--map-tokens`). | none (docs/credits) |

### 1.4 Licence obligations (Aider)
- **Code:** Apache-2.0. CodeForge should **re-implement** the algorithm. Ideas and heuristics are not copyrightable, and the constants are facts. If any Aider code is copied or closely transliterated:
  - ship the Apache-2.0 text;
  - keep Aider's attribution (`Copyright Aider-AI / Paul Gauthier`, per the repo);
  - add a prominent "modified by CodeForge" notice in the changed files.

  There is no NOTICE file to propagate. Recommended either way: a `THIRD_PARTY_NOTICES` / README credit such as "repo-map ranking approach inspired by Aider (Apache-2.0)".
- **Query files in Aider's repo:**
  - `queries/tree-sitter-languages/README.md` says they are "modified versions of the tags.scm files" from the upstream grammar repos, and lists tree-sitter-python and tree-sitter-javascript as **MIT**.
  - `queries/tree-sitter-language-pack/README.md` points to the Goldziher/tree-sitter-language-pack source list for the per-repo licences. For Python and JS that list resolves to the same tree-sitter org MIT grammars.
  - Aider's only change is renaming `@name`, and in the JS file also dropping the export pattern.
- **Verdict:** **Yes, CodeForge can vendor `python-tags.scm` and `javascript-tags.scm` with attribution.**
  - The cleanest provenance is the one done here: take the files from the MIT upstream (the `tree_sitter_python` / `tree_sitter_javascript` 0.25.0 wheels, `queries/tags.scm`) and apply the capture rename ourselves.
  - Then only MIT applies: keep the copyright line and the MIT permission notice alongside the files.
  - Copying Aider's versions verbatim would also be permitted: Apache-2.0 is compatible, so add the Apache text plus a note of Aider's modification. It is just unnecessary.

---

## Aider / tree-sitter — 2. py-tree-sitter (and the installed grammar wheels)

- URL: https://github.com/tree-sitter/py-tree-sitter
- Commit: `4a8753910f5bbbd4368ad88fe1357a823506aa53` (2026-11-17, "fix(query): prevent double free of predicate"). `pyproject.toml` says `0.26.1`.
- SPDX licence: `MIT` (Copyright (c) 2019 Max Brunsfeld, GitHub)
- **Caveat:** the clone's docs mark `Query.copy()` / `__copy__` as `versionadded 0.27.0`, and the installed **0.26.1 does not have them** (verified from `dir(Query)`). Treat the clone's docs as slightly ahead of the release, and do not rely on `Query.copy`.
- Grammar wheels (installed):
  - `tree-sitter-python 0.25.0`: `MIT`, Copyright (c) 2016 Max Brunsfeld, https://github.com/tree-sitter/tree-sitter-python
  - `tree-sitter-javascript 0.25.0`: `MIT`, Copyright (c) 2014 Max Brunsfeld, https://github.com/tree-sitter/tree-sitter-javascript
  - Both report `abi_version 15`. The binding supports ABI 13 to 15.

### 2.1 Key files and functions

| File | Item | Finding |
|---|---|---|
| `tree_sitter/__init__.pyi` | `Language(ptr)` | `Language(tree_sitter_python.language())`. `Language.query()` **no longer exists** in 0.26 (verified). |
| `tree_sitter/__init__.pyi` | `Parser(language)` | `Parser(LANG)` or `p.language = LANG`. `parse(bytes)` or `parse(read_callback)`. |
| `tree_sitter/__init__.pyi` | `Query(language, source)` | Compiles or raises `QueryError` (a subclass of `ValueError`). It has **no** `captures`/`matches` methods. |
| `tree_sitter/__init__.pyi` | `QueryCursor(query, *, match_limit=0xFFFFFFFF)` | `.captures(node, predicate=None, progress_callback=None) -> dict[str, list[Node]]`. `.matches(node, ...) -> list[tuple[int, dict[str, list[Node]]]]`. It also has `set_byte_range`, `set_point_range`, `set_max_start_depth`, and `did_exceed_match_limit`. |
| `tree_sitter/binding/query_cursor.c` | `captures` | Per capture name, the nodes are **de-duplicated** (insertion-ordered dict, then converted to a list), in document order. This is verified, so no extra de-duplication is needed. |
| `tree_sitter/binding/query.c` | Predicate parsing | Built-ins: `#eq?`/`#not-eq?`/`#any-eq?`/`#any-not-eq?`, `#match?`/`#not-match?`/`#any-match?`/`#any-not-match?`, `#any-of?`/`#not-any-of?`, `#is?`/`#is-not?`, and `#set!`. **Any other predicate** (for example `#strip!` or `#select-adjacent!`) compiles into a `QueryPredicateGeneric`. |
| `tree_sitter/binding/query_predicates.c` | `query_satisfies_predicates` | Generic predicates are evaluated **only if a `predicate` callable is passed**, and are otherwise silently treated as satisfied. All predicates are skipped if `tree.source` is None. Both `parse(bytes)` and `parse(callback)` store a source, and with a callback-parsed tree `#not-match?` was still enforced (verified). |
| `examples/usage.py` | Usage | Canonical `Query` + `QueryCursor` usage. `captures["name"][0]` is a `Node`. |
| site-packages `tree_sitter_python/queries/` | Shipped queries | `tags.scm`, `highlights.scm`. Exposed as `tree_sitter_python.TAGS_QUERY`. |
| site-packages `tree_sitter_javascript/queries/` | Shipped queries | `tags.scm`, `highlights.scm`, `highlights-jsx.scm`, `highlights-params.scm`, `injections.scm`, `locals.scm`. Exposed as `tree_sitter_javascript.TAGS_QUERY` (plus `LOCALS_QUERY` and others). |

### 2.2 How to run queries in 0.26 (verified)
- `Query(lang, src)` compiles the query. `QueryCursor(query)` executes it. `QueryCursor.captures(root)` **does** return a `dict` mapping each capture name to a list of `Node`s.
- `captures()` flattens across patterns. That is why the kind must be encoded in the name capture (`name.definition.class`). The alternative is `matches()`, which keeps each match's captures together. There the upstream single `@name` capture pairs with the sibling `definition.X` / `reference.X` key.
- `Node.text` returns `bytes`. `Node.start_point` is a `Point(row, column)`, 0-based.

**Compile results against the 0.25 grammars (verified):**

| Query | Result |
|---|---|
| Aider tsl-pack `python-tags.scm` | OK (4 patterns) |
| Aider legacy `python-tags.scm` | OK (3 patterns; no constants) |
| upstream 0.25.0 python `tags.scm` | OK (4 patterns, `@name`) |
| Aider tsl-pack `javascript-tags.scm` | OK (10 patterns) |
| Aider legacy `javascript-tags.scm` | **FAIL**: `Invalid node type at row 27, column 5: function` |
| upstream 0.25.0 javascript `tags.scm` | OK (11 patterns, `@name`) |
| **CodeForge vendored `python-tags.scm`** | OK. Defs: constant/class/function; refs: call. |
| **CodeForge vendored `javascript-tags.scm`** | OK (11 patterns). `require` is filtered and `constructor` is filtered. `new ns.Widget()` gives `Widget`. Covers `handler`, `arrowProp`, generator, and `export default answer = 42` as a constant. |

**Fixes and changes applied to the vendored files:**
1. Both files: `@name` is renamed to `@name.definition.<kind>` / `@name.reference.<kind>`, so the flat `captures()` dict carries the kind.
2. JS: `(new_expression constructor: (_) @name...)` becomes `[(identifier) (member_expression property: (property_identifier))]`. Aider's original yields `"ns.Widget"`, which never matches the def `Widget` (verified).
3. JS: kept upstream 0.25.0's `export_statement ... @definition.constant` pattern, which is missing from Aider's file.
4. JS: `#strip!` / `#select-adjacent!` and the `@doc` capture are left as no-ops. They are documented in the header and harmless.

**Optional extra Python reference patterns (verified to compile and match; not in the vendored file):**
```scheme
(class_definition superclasses: (argument_list
  [(identifier) @name.reference.class (attribute attribute: (identifier) @name.reference.class)]))
(decorator [(identifier) @name.reference.call (attribute attribute: (identifier) @name.reference.call)])
(import_from_statement name: (dotted_name (identifier) @name.reference.import))
(type (identifier) @name.reference.type)
```
These add inheritance, decorator, `from x import Y`, and annotation edges. The stock query only sees calls, so `class A(Base)` creates no edge to `Base`.

### 2.3 Minimal working snippet (verified verbatim, 19 lines)
```python
from pathlib import Path
import tree_sitter_python as tsp
from tree_sitter import Language, Parser, Query, QueryCursor

LANG = Language(tsp.language())
PARSER = Parser(LANG)
QUERY = Query(LANG, Path("queries/python-tags.scm").read_text(encoding="utf-8"))

def extract_tags(source: bytes):
    captures = QueryCursor(QUERY).captures(PARSER.parse(source).root_node)  # dict[str, list[Node]]
    for capture_name, nodes in captures.items():
        if capture_name.startswith("name.definition."):
            kind = "def"
        elif capture_name.startswith("name.reference."):
            kind = "ref"
        else:
            continue
        for node in nodes:
            yield kind, node.text.decode("utf-8"), node.start_point.row + 1
```
Output for `class A:\n    def run(self):\n        helper()\n`:
`[('def','A',1), ('def','run',2), ('ref','helper',3)]`.
JavaScript works the same way with `tree_sitter_javascript` and `javascript-tags.scm`.

**Option B (no vendoring):** use `tsp.TAGS_QUERY` and `QueryCursor(q).matches(root)`. For each `(idx, caps)`, the role is the key starting with `definition.` or `reference.`, and the name node is `caps["name"]`. This is verified for both languages (`upstream_matches.py`). Vendoring is still preferable: CodeForge controls fixes and extra patterns, and the file is pinned to the grammar version.

### 2.4 Mapping to CodeForge

| Source file | Original purpose | Functionality selected | CodeForge destination |
|---|---|---|---|
| `tree_sitter/__init__.pyi` (`Language`, `Parser`) | Typed API | Build `Language(tsp.language())` / `Language(tsj.language())` once per language and cache `Parser` per language. Parse `bytes`. | `src/codeforge/repository/parser.py` |
| `tree_sitter/__init__.pyi` (`Query`, `QueryError`) | Query compilation | Compile each `.scm` once at startup or lazily, and raise a clear error on `QueryError`. | `src/codeforge/repository/parser.py` |
| `tree_sitter/__init__.pyi` / `binding/query_cursor.c` (`QueryCursor.captures`) | Query execution | `QueryCursor(query).captures(root)` gives a de-duplicated `dict[str, list[Node]]`. Map it to `(kind, name, line)` by capture-name prefix. | `src/codeforge/repository/symbol_extractor.py` |
| `binding/query.c`, `binding/query_predicates.c` | Predicate semantics | Know-how: built-ins are enforced; unknown `#…!` predicates are no-ops unless you pass a callable. | `src/codeforge/repository/symbol_extractor.py` (comments/tests) |
| site-packages `tree_sitter_python/queries/tags.scm` | Upstream Python tags | Vendored with renamed captures. | `src/codeforge/repository/queries/python-tags.scm` |
| site-packages `tree_sitter_javascript/queries/tags.scm` | Upstream JS tags | Vendored with renamed captures plus the `new_expression` fix. | `src/codeforge/repository/queries/javascript-tags.scm` |
| `examples/usage.py` | API example | The pattern only; nothing copied. | `src/codeforge/repository/parser.py` |

### 2.5 Licence obligations (py-tree-sitter and grammars)
- **py-tree-sitter (MIT):** it is used as a dependency only, so no vendoring obligation. If any example code is copied, include the MIT notice (Copyright (c) 2019 Max Brunsfeld, GitHub).
- **Vendored `python-tags.scm` (MIT, Copyright (c) 2016 Max Brunsfeld):** keep the SPDX and copyright header that is already in the file, ship `LICENSE-tree-sitter-python` (the exact MIT text) next to it, and list it in `THIRD_PARTY_NOTICES`.
- **Vendored `javascript-tags.scm` (MIT, Copyright (c) 2014 Max Brunsfeld):** the same, with `LICENSE-tree-sitter-javascript`.
- **Packaging:** make sure the `queries/*.scm` and `LICENSE-*` files are included in the wheel, for example with hatch/setuptools package-data.
- **Not verified locally:** the licences of `grep-ast` and `tree-sitter-language-pack`. Neither is needed if CodeForge uses the per-language wheels and its own renderer.
