"""Integration tests: real Docker sandbox and real Harbor trials on a hand-written fixture task.
Skipped automatically when Docker or Harbor is unavailable."""

import manual_task
import pytest

from codeforge.environment.docker_builder import DockerSandbox
from codeforge.environment.environment_validator import check_image_for_shortcuts, run_baseline
from codeforge.environment.profile_builder import build_environment
from codeforge.harbor import harbor_validator, task_builder
from codeforge.repository import profiles
from codeforge.schemas.task import TestFile
from codeforge.validation import engine

docker_ok = DockerSandbox().version() is not None
harbor_ok = harbor_validator.harbor_version() is not None
pytestmark = pytest.mark.skipif(not docker_ok, reason="Docker engine not reachable")


@pytest.fixture(scope="module")
def env(sample_checkout, sample_profile, tmp_path_factory):
    adapter = profiles.adapter_by_name(sample_profile.adapter)
    work = tmp_path_factory.mktemp("env")
    spec = build_environment(sample_profile, sample_checkout.snapshot_dir, work / "env", adapter,
                             DockerSandbox(), work / "logs")
    baseline = run_baseline(sample_profile, adapter, spec.image_tag, DockerSandbox(),
                            work / "baseline", runs=2)
    sample_profile.baseline_test_status = baseline
    return adapter, spec, baseline, work


@pytest.mark.docker
def test_baseline_and_image_are_clean(env):
    adapter, spec, baseline, work = env
    assert baseline.healthy and len(baseline.passed) == 27 and not baseline.flaky
    assert check_image_for_shortcuts(spec.image_tag, DockerSandbox(), work / "sc") == []


@pytest.mark.docker
def test_controls_detect_missing_and_wrong_behaviour(env, sample_checkout):
    adapter, spec, baseline, work = env
    money = (sample_checkout.snapshot_dir / "shopcart" / "money.py").read_text()
    task = manual_task.build(money, sample_checkout.sha, sample_checkout.url)
    ctx = engine.ValidationContext(adapter, spec.image_tag, spec.image_tag, DockerSandbox(),
                                   baseline, ["tests"], work / "val")
    res = engine.run_controls(ctx, task.feature_test_files, task.reference,
                              {"shopcart/money.py": money}, "fixture")
    status = {g.gate.value: g.status.value for g in res["gates"]}
    assert status == {"positive_control": "passed", "negative_control": "passed",
                      "regression": "passed", "stability": "passed"}
    ast_res, _ = engine.run_mutation(ctx, task.feature_test_files, task.reference,
                                     {"shopcart/money.py": money}, [], "fixture")
    assert ast_res.total > 0 and ast_res.killed > 0
    # a test that does not exercise the feature must be caught by the negative control
    weak = [TestFile(path="tests/test_codeforge_weak.py",
                     content="def test_trivial():\n    assert 1 + 1 == 2\n")]
    res2 = engine.run_controls(ctx, weak, task.reference, {"shopcart/money.py": money}, "weak")
    neg = next(g for g in res2["gates"] if g.gate.value == "negative_control")
    assert neg.status.value == "failed"


@pytest.mark.harbor
@pytest.mark.skipif(not harbor_ok, reason="Harbor CLI not installed")
def test_harbor_oracle_and_nop(env, sample_checkout, sample_profile, tmp_path):
    adapter, spec, baseline, work = env
    money = (sample_checkout.snapshot_dir / "shopcart" / "money.py").read_text()
    task = manual_task.build(money, sample_checkout.sha, sample_checkout.url)
    task.feature_test_ids = [f"tests.test_codeforge_fixture::{n}" for n in (
        "test_positive_amount_unchanged", "test_negative_amount_becomes_zero",
        "test_zero_stays_zero")]
    task.regression_test_ids = baseline.passed
    d = task_builder.build_task("codeforge", task, sample_profile, adapter, spec.env_dir,
                                sample_checkout.snapshot_dir, ["tests"], tmp_path / "tasks",
                                {"status": "fixture", "validity_score": 0, "gates": []}, {})
    assert harbor_validator.lint(d).ok
    oracle = harbor_validator.run_trial(d, tmp_path / "jobs", "oracle", "it-oracle")
    nop = harbor_validator.run_trial(d, tmp_path / "jobs", "nop", "it-nop")
    assert oracle.reward == 1.0 and nop.reward == 0.0
