# Source integration manifest

How each upstream project contributes to CodeForge AI. Three kinds of integration are
used, and every row says which one applies:

- **Vendored**: third-party files copied into this repository, with license and
  modification notice kept.
- **Re-implemented**: CodeForge's own code implementing an upstream algorithm or design,
  with credit and no upstream code copied.
- **Dependency**: installed as a pinned package (`pyproject.toml` + `uv.lock`) or a pinned
  tool, never copied.

Upstream commits are listed in [upstream-research.md](upstream-research.md). The
machine-readable copy is [`third_party/manifest.yaml`](../third_party/manifest.yaml).

## Vendored files

| Source repository | Source file | Original purpose | Functionality selected | Destination | Changes |
|---|---|---|---|---|---|
| tree-sitter-python 0.25.0 (MIT) | `queries/tags.scm` | Code-navigation tags for GitHub | Definition/reference captures for Python | `src/codeforge/repository/queries/python-tags.scm` | Captures renamed to `name.definition.*` / `name.reference.*`; SPDX + copyright header and modification notice added |
| tree-sitter-javascript 0.25.0 (MIT) | `queries/tags.scm` | Code-navigation tags | Definition/reference captures for JavaScript | `src/codeforge/repository/queries/javascript-tags.scm` | Same renaming; `new ns.Foo()` now yields `Foo`; header added |

License texts: `licenses/tree-sitter-python-MIT.txt`, `licenses/tree-sitter-javascript-MIT.txt`.

## Re-implemented designs

| Source repository | Source file | Original purpose | Functionality selected | CodeForge destination |
|---|---|---|---|---|
| Aider (Apache-2.0) | `aider/repomap.py` (`get_tags_raw`, `get_ranked_tags`, `get_ranked_tags_map`) | Ranked repo map for chat context | File graph from def/ref identifiers, edge multipliers (mentioned ×10, long snake/camel ×10, private ×0.1, defined in >5 files ×0.1, √refs), personalised PageRank, rank flowing to definitions, binary search to fit a token budget, cache key | `repository/repo_mapper.py` (own PageRank, no networkx; cache keyed by commit SHA + file hashes) |
| Aider (Apache-2.0) | SEARCH/REPLACE edit format (`aider/coders/editblock_*`) | LLM file edits | Exact-match blocks with whitespace-tolerant fallback | `generation/patch_generator.py` |
| SWE-smith (MIT) | `swesmith/profiles/base.py` (`RepoProfile`, registry) | Per-repo install/test recipes | Profile registry concept: one recipe object per ecosystem, optional per-repo override | `repository/profiles.py`, `environment/profile_builder.py`, `adapters/languages/*` |
| SWE-smith (MIT) | `swesmith/harness/valid.py`, `harness/gather.py` | Keep only bug candidates that break tests | Validate by execution; accept only with ≥1 FAIL_TO_PASS and ≥1 PASS_TO_PASS; reject on timeout | `validation/engine.py` (negative, positive and regression controls) |
| SWE-smith (MIT) | `swesmith/harness/utils.py` (`get_valid_report`) | Compare test status before/after | Per-test status comparison between original and modified code | `validation/engine.py`, `harbor/templates/grade.py` |
| SWE-smith (MIT) | `swesmith/issue_gen/` | LLM-written issue text | Separate model call that writes the task statement | `generation/task_generator.py` |
| SWE-bench (MIT) | `swebench/harness/run_evaluation.py`, `grading.py` | Apply patch in Docker, grade F2P/P2P | Per-instance Docker run, JUnit-based per-test grading, all-or-nothing resolution | `validation/test_runner.py`, `harbor/templates/grade.py` |
| SWE-Gym (Apache-2.0) | README note on the git shortcut (cf. SWE-bench issue #465) | Known reward hack | Agent images must not contain git history, future commits or solution | `repository/git_manager.py` (`export_tree`: `git archive`, no `.git`), `environment/environment_validator.py` (`check_image_for_shortcuts`), `validation/leakage_checker.py` |
| Harbor (Apache-2.0) | `adapters/swebench/.../task-template` | SWE-bench → Harbor tasks | Gold patch written by `solve.sh`; `test.sh` runs tests and writes the reward | `harbor/solution_packager.py`, `harbor/test_packager.py` |
| mutmut (BSD-3-Clause) | operator families in `mutmut/node_mutation.py` | Python mutation testing | Classic operators (comparison, arithmetic, boolean, constants, return, condition, raise) | `validation/mutation_validator.py` (diff-scoped AST engine) |

Nothing from Aider, SWE-smith, SWE-bench, SWE-Gym, Harbor or mutmut is copied verbatim.
The modules above carry docstrings that credit their source.

## Dependencies (installed, pinned)

| Package | Version | License | Used for |
|---|---|---|---|
| harbor (CLI, `uv tool install harbor`) | 0.26.0 | Apache-2.0 | `harbor init`, `harbor lint`, `harbor run -a oracle/nop/<agent>` |
| litellm | 1.110.1 | MIT | Provider-agnostic model calls (Gemini free tier, Ollama) |
| pydantic / pydantic-settings | 2.14.4 / 2.16.3 | MIT | All data contracts, validated LLM output, config |
| tree-sitter | 0.26.1 | MIT | Parsing |
| tree-sitter-python / -javascript | 0.25.0 / 0.25.0 | MIT | Grammars |
| typer | 0.29.2 | MIT | CLI |
| fastapi / uvicorn | 0.165.0 / 0.54.0 | MIT / BSD-3-Clause | Dashboard API |
| pytest / pytest-cov | 9.2.0 / 7.1.0 | MIT | CodeForge's own tests; pytest also runs inside target containers |
| hypothesis | 6.170.16 | MPL-2.0 | Property-based tests of CodeForge itself (`tests/unit/test_properties.py`); unmodified, so MPL file-level obligations do not apply |
| coverage | 7.17.3 | Apache-2.0 | Changed-line coverage, installed only in the validation image |

## Studied but not integrated

| Project | Why |
|---|---|
| SWE-smith task datasets / images | Not needed. CodeForge generates feature tasks and does not reuse bug instances. |
| SWE-Gym environment archives | They contain the git shortcut, and we build our own environments anyway. |
| SWE-bench evaluation harness (as a dependency) | Harbor is the required execution interface, so CodeForge does not bundle a second harness. |
| mutmut (as a runtime tool) | mutmut 3 mutates whole modules through its own trampoline and project copy. CodeForge needs mutation restricted to the lines the reference changed, so the operators were re-implemented. |
| networkx | `pagerank` needs numpy/scipy. A 30-line power iteration avoids two heavy dependencies. |

## Cleanup

`research/upstream/` holds the shallow clones used for this analysis. It is excluded by
`.gitignore` and can be deleted at any time: nothing imports from it. License texts were
copied to `licenses/` beforehand.
