# Security model

Target repositories and all generated code are **untrusted**.

| Control | Where |
|---|---|
| All target/generated code runs in Docker, never on the host | `environment/docker_builder.py` |
| `--network none` during validation; verifier `network_mode = "no-network"` in Harbor | `docker_builder.run_script`, `harbor/metadata_builder.py` |
| CPU, memory, swap and PID limits; per-step `timeout` | `config.py`, `validation/test_runner.py` |
| `--cap-drop ALL`, `no-new-privileges`, tmpfs `/tmp`, no privileged containers | `docker_builder.run_script` |
| No host bind mounts and no Docker socket in containers (files move via `docker cp`) | `docker_builder.run_script` |
| Subprocess calls take argument lists only; `shell=False` enforced | `utils/proc.py` |
| Path-traversal protection for every model-supplied path; `.git` writes refused | `utils/fs.py` (`safe_relpath`, `resolve_inside`) |
| Safe archive extraction (`tarfile` data filter, zip slip and symlink checks) | `repository/git_manager.py`, `utils/fs.py` |
| Repository size limit | `git_manager.checkout` (`max_repo_mb`) |
| Dirty working trees refused by default | `git_manager.checkout` (`DirtyPolicy`) |
| The original repository is never modified (in-memory worktree, `git archive` snapshot) | `generation/patch_generator.py`, `git_manager.export_tree` |
| Secrets only from the environment or `.env`; redacted in logs; packages scanned for key patterns | `logging_config.py`, `validation/leakage_checker.py` |
| Agent image has no git history, tests, solution or secrets (checked inside the image) | `environment_validator.check_image_for_shortcuts` |
| Verifier ignores agent-planted pytest and interpreter hooks; pristine tests restored | `harbor/test_packager.py` |
| Dashboard binds to 127.0.0.1; repository input validated; one run at a time | `web/server.py` |

Known residual risks:
- Dependency installation during image builds needs network access and runs the
  repository's own install steps inside the container build. It is never run on the host.
- An agent could special-case the hidden tests' inputs. The tests stay hidden from the agent
  and are derived from the spec, which reduces but cannot eliminate this risk.
