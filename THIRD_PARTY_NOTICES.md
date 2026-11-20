# Third-party notices

CodeForge AI (Team TECH TITAN) includes or builds on the following third-party work.
Full license texts are in [`licenses/`](licenses/). Details of each integration are in
[`docs/source-integration-manifest.md`](docs/source-integration-manifest.md).

## Vendored source files

### tree-sitter-python tags query
- File: `src/codeforge/repository/queries/python-tags.scm`
- Source: https://github.com/tree-sitter/tree-sitter-python (v0.25.0, `queries/tags.scm`)
- Copyright (c) 2016 Max Brunsfeld. MIT License (`licenses/tree-sitter-python-MIT.txt`)
- Modified by CodeForge: capture names changed to `name.definition.*` / `name.reference.*`;
  header added.

### tree-sitter-javascript tags query
- File: `src/codeforge/repository/queries/javascript-tags.scm`
- Source: https://github.com/tree-sitter/tree-sitter-javascript (v0.25.0, `queries/tags.scm`)
- Copyright (c) 2014 Max Brunsfeld. MIT License (`licenses/tree-sitter-javascript-MIT.txt`)
- Modified by CodeForge: capture names changed; constructor references through member
  expressions resolve to the class name; header added.

## Designs re-implemented with credit (no code copied)

- **Aider** (https://github.com/Aider-AI/aider, Apache-2.0, `licenses/aider-Apache-2.0.txt`):
  ranked repository map algorithm (`aider/repomap.py`) and the SEARCH/REPLACE edit format.
- **SWE-smith** (https://github.com/SWE-bench/SWE-smith, MIT, `licenses/SWE-smith-MIT.txt`):
  repository profiles and validate-by-execution filtering (FAIL_TO_PASS / PASS_TO_PASS).
- **SWE-bench** (https://github.com/SWE-bench/SWE-bench, MIT, `licenses/SWE-bench-MIT.txt`):
  Docker-isolated patch evaluation and per-test grading.
- **SWE-Gym** (https://github.com/SWE-Gym/SWE-Gym, Apache-2.0, `licenses/SWE-Gym-Apache-2.0.txt`):
  the documented git-history reward shortcut, which CodeForge environments are built to prevent.
- **Harbor** (https://github.com/harbor-framework/harbor, Apache-2.0,
  `licenses/harbor-Apache-2.0.txt`): task interface and the swebench adapter's package shape.
- **mutmut** (https://github.com/boxed/mutmut, BSD-3-Clause): mutation operator families.

## Runtime dependencies

These are installed from PyPI, never copied. Versions are pinned in `pyproject.toml` and `uv.lock`:
Harbor (Apache-2.0), LiteLLM (MIT), Pydantic (MIT), pydantic-settings (MIT),
py-tree-sitter (MIT, `licenses/py-tree-sitter-MIT.txt`), tree-sitter-python (MIT),
tree-sitter-javascript (MIT), Typer (MIT), FastAPI (MIT), Uvicorn (BSD-3-Clause),
pytest (MIT), pytest-cov (MIT), Hypothesis (MPL-2.0, unmodified, development only),
coverage.py (Apache-2.0, validation image only).
