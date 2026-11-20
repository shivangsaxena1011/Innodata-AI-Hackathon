import importlib.util
import json
from importlib import resources

from codeforge.adapters.testing import junit
from codeforge.adapters.testing.junit import parse_junit

JUNIT = """<?xml version="1.0"?><testsuites><testsuite name="pytest">
<testcase classname="tests.test_a" name="test_ok"/>
<testcase classname="tests.test_a" name="test_bad"><failure message="x"/></testcase>
<testcase classname="tests.test_a" name="test_err"><error message="x"/></testcase>
<testcase classname="tests.test_a" name="test_skip"><skipped/></testcase>
</testsuite></testsuites>"""


def _grade_module():
    path = resources.files("codeforge.harbor.templates").joinpath("grade.py")
    spec = importlib.util.spec_from_file_location("grade", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parse_junit_statuses(tmp_path):
    p = tmp_path / "r.xml"
    p.write_text(JUNIT)
    r = parse_junit(p)
    assert r.passed == ["tests.test_a::test_ok"]
    assert r.failed == ["tests.test_a::test_bad"]
    assert r.errors == ["tests.test_a::test_err"]
    assert r.skipped == ["tests.test_a::test_skip"]


def test_missing_report_is_flagged(tmp_path):
    assert parse_junit(tmp_path / "nope.xml").parse_error


def test_grader_ids_match_codeforge_ids():
    grade = _grade_module()
    for cls, name in [("tests.test_a", "test_x"), ("", "test_y"), ("t.T", "test_z[1-2]")]:
        assert grade.test_id(cls, name) == junit.test_id(cls, name)


def test_grader_reward_rules(tmp_path):
    grade = _grade_module()
    feature = tmp_path / "feature.xml"
    regression = tmp_path / "regression.xml"
    feature.write_text(JUNIT)
    regression.write_text(JUNIT)
    expected = tmp_path / "expected.json"
    reward = tmp_path / "reward.json"

    expected.write_text(json.dumps({"feature_tests": ["tests.test_a::test_ok"],
                                    "regression_tests": ["tests.test_a::test_ok"]}))
    grade.main(["g", str(expected), str(feature), str(regression), str(reward)])
    assert json.loads(reward.read_text())["reward"] == 1.0

    # skipped / failing / missing tests all count as not passed
    for bad in ("tests.test_a::test_skip", "tests.test_a::test_bad", "tests.test_a::missing"):
        expected.write_text(json.dumps({"feature_tests": ["tests.test_a::test_ok", bad],
                                        "regression_tests": []}))
        grade.main(["g", str(expected), str(feature), str(regression), str(reward)])
        data = json.loads(reward.read_text())
        assert data["reward"] == 0.0 and data["feature_pass_rate"] == 0.5


def test_grader_handles_missing_reports(tmp_path):
    grade = _grade_module()
    expected = tmp_path / "expected.json"
    expected.write_text(json.dumps({"feature_tests": ["a::b"], "regression_tests": ["c::d"]}))
    reward = tmp_path / "reward.json"
    grade.main(["g", str(expected), str(tmp_path / "x.xml"), str(tmp_path / "y.xml"), str(reward)])
    assert json.loads(reward.read_text())["reward"] == 0.0
