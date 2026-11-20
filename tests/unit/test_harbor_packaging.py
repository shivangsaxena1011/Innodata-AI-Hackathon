import base64
import re
import tomllib

import manual_task

from codeforge.adapters.languages.python_adapter import PythonAdapter, choose_python
from codeforge.environment.profile_builder import write_environment
from codeforge.harbor import task_builder
from codeforge.harbor.solution_packager import build_solve_sh
from codeforge.validation.leakage_checker import check_package


def _build(tmp_path, sample_checkout, sample_profile, monkeypatch):
    monkeypatch.setattr("codeforge.harbor.task_builder.harbor_executable", lambda: None)
    adapter = PythonAdapter()
    env = write_environment(sample_profile, sample_checkout.snapshot_dir, tmp_path / "env",
                            adapter, "python:3.12-slim@sha256:" + "0" * 64)
    money = (sample_checkout.snapshot_dir / "shopcart" / "money.py").read_text()
    task = manual_task.build(money, sample_checkout.sha, sample_checkout.url)
    task.feature_test_ids = ["tests.test_codeforge_fixture::test_zero_stays_zero"]
    task.regression_test_ids = ["tests.test_cart::test_add_and_subtotal"]
    d = task_builder.build_task("codeforge", task, sample_profile, adapter, env.env_dir,
                                sample_checkout.snapshot_dir, ["tests"], tmp_path / "out",
                                {"status": "valid", "validity_score": 90.0, "gates": []}, {})
    return d, task


def test_package_layout_and_task_toml(tmp_path, sample_checkout, sample_profile, monkeypatch):
    d, task = _build(tmp_path, sample_checkout, sample_profile, monkeypatch)
    for rel in ("instruction.md", "task.toml", "environment/Dockerfile", "solution/solve.sh",
                "tests/test.sh", "tests/Dockerfile", "tests/grade.py", "tests/expected.json",
                "tests/feature/tests/test_codeforge_fixture.py", "task_manifest.json"):
        assert (d / rel).exists(), rel
    cfg = tomllib.loads((d / "task.toml").read_text())
    assert cfg["schema_version"] == "1.4"
    assert cfg["verifier"]["environment_mode"] == "separate"
    assert cfg["metadata"]["starting_commit_sha"] == sample_checkout.sha
    assert cfg["artifacts"][0]["source"] == "/app"
    assert b"\r\n" not in (d / "tests" / "test.sh").read_bytes()
    # agent image never receives tests or solution
    dockerfile = (d / "environment" / "Dockerfile").read_text()
    assert "tests/" not in dockerfile and "solution" not in dockerfile
    assert not (d / "environment" / "repo" / "tests" / "test_codeforge_fixture.py").exists()
    assert check_package(d, task) == []


def test_test_sh_writes_reward_first_and_strips_hooks(tmp_path, sample_checkout, sample_profile,
                                                       monkeypatch):
    d, _ = _build(tmp_path, sample_checkout, sample_profile, monkeypatch)
    sh = (d / "tests" / "test.sh").read_text()
    assert sh.index("reward.json") < sh.index("pytest")
    assert "sitecustomize.py" in sh and "conftest.py" in sh
    assert "./tests/conftest.py" in sh  # pristine conftest is kept


def test_solve_sh_round_trips_content():
    from codeforge.schemas.task import FileChange, ReferenceSolution

    content = "x = '''$HOME `cmd` \\n'''\nprint(\"ünïcode\")\n"
    sh = build_solve_sh(ReferenceSolution(explanation="", unified_diff="",
                                          changes=[FileChange(path="a/b.py", action="create",
                                                              content=content)]))
    b64 = re.search(r"<<'CODEFORGE_EOF_0'\n(.*?)\nCODEFORGE_EOF_0", sh, re.S).group(1)
    assert base64.b64decode(b64.replace("\n", "")).decode() == content


def test_leakage_checker_catches_leaks(tmp_path, sample_checkout, sample_profile, monkeypatch):
    d, task = _build(tmp_path, sample_checkout, sample_profile, monkeypatch)
    (d / "instruction.md").write_text(
        "Run /tests/test.sh and see test_negative_amount_becomes_zero")
    problems = check_package(d, task)
    assert any("/tests" in p for p in problems)


def test_choose_python():
    assert choose_python(">=3.10") == "3.13"
    assert choose_python(">=3.8,<3.12") == "3.11"
    assert choose_python(None) == "3.12"


def test_leakage_allows_disclosed_contract_text(tmp_path, sample_checkout, sample_profile,
                                                monkeypatch):
    d, task = _build(tmp_path, sample_checkout, sample_profile, monkeypatch)
    signature = task.spec.contract[0].signature
    logic = "secret_logic_line = compute_the_value(amount) * 2"
    task.reference.unified_diff = f"+++ b/x.py\n+{signature}:\n+    {logic}\n"
    (d / "instruction.md").write_text(f"Implement `{signature}`\n")
    assert check_package(d, task) == []
    (d / "instruction.md").write_text(f"hint: {logic}\n")
    assert any("reference code" in p for p in check_package(d, task))


def test_agent_outcome_classification():
    from codeforge.evaluation.agent_runner import classify
    from codeforge.harbor.harbor_validator import TrialOutcome

    assert classify(TrialOutcome("a", True, 1.0)) == "solved"
    assert classify(TrialOutcome("a", True, 0.0)) == "unsolved"
    assert classify(TrialOutcome("a", False, None, exception="429 RESOURCE_EXHAUSTED")) == \
        "quota_error"
    assert classify(TrialOutcome("a", False, None, exception="docker died")) == "error"
