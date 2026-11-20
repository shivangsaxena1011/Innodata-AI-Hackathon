import json

import pytest

from codeforge.ai.llm_client import ScriptedLLM
from codeforge.ai.structured_output import StructuredOutputError, extract_json, generate
from codeforge.generation.patch_generator import (
    EditError,
    Worktree,
    apply_edits,
    changed_lines,
    to_file_changes,
    unified_diff,
)
from codeforge.schemas.task import DiscoveryResponse, FileEdit


def test_extract_json_variants():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": {"b": "}"}} trailing') == {"a": {"b": "}"}}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_structured_output_retries_with_validation_error():
    good = {"candidates": [{
        "title": "t", "archetype": "business_rule", "problem_statement": "p",
        "requirements": ["a", "b"], "acceptance_criteria": ["x", "y"],
        "affected_modules": ["m.py"],
        "contract": [{"kind": "function", "module": "m", "name": "f", "signature": "def f()",
                      "behaviour": "b"}]}]}
    llm = ScriptedLLM({"disc": ['{"candidates": []}'], "disc#retry1": [json.dumps(good)]})
    res = generate(llm, DiscoveryResponse, "sys", "user", "disc")
    assert res.value.candidates[0].title == "t"
    assert [a["ok"] for a in res.attempts] == [False, True]
    assert "failed validation" in llm.prompts[1][2]


def test_structured_output_gives_up():
    llm = ScriptedLLM({"x": ["nope"], "x#retry1": ["nope"], "x#retry2": ["nope"]})
    with pytest.raises(StructuredOutputError):
        generate(llm, DiscoveryResponse, "s", "u", "x")


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("def a():\n    return 1\n\n\ndef b():\n    return 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_m.py").write_text("def test_x():\n    assert True\n")
    return Worktree(tmp_path)


def test_apply_exact_and_fuzzy_edits(tree):
    apply_edits(tree, [FileEdit(path="pkg/m.py", search="def a():\n    return 1",
                                replace="def a():\n    return 2")])
    apply_edits(tree, [FileEdit(path="pkg/m.py", search="  def b():  \n      return 1",
                                replace="  def b():\n      return 3")])
    assert "return 2" in tree.read("pkg/m.py") and "    return 3" in tree.read("pkg/m.py")
    changes = to_file_changes(tree)
    assert changes[0].action == "modify" and "+    return 2" in unified_diff(tree, changes)
    assert (tree.root / "pkg" / "m.py").read_text().count("return 1") == 2  # disk untouched


def test_edit_errors(tree):
    with pytest.raises(EditError, match="occurs 2 times"):
        apply_edits(tree, [FileEdit(path="pkg/m.py", search="return 1", replace="x")])
    with pytest.raises(EditError, match="not found"):
        apply_edits(tree, [FileEdit(path="pkg/m.py", search="nothing", replace="x")])
    with pytest.raises(EditError, match="test file"):
        apply_edits(tree, [FileEdit(path="tests/test_m.py", search="True", replace="False")])


def test_create_file_and_changed_lines(tree):
    apply_edits(tree, [FileEdit(path="pkg/new.py", search="", replace="X = 1")])
    assert to_file_changes(tree)[0].action == "create"
    assert changed_lines("a\nb\nc\n", "a\nB\nc\nd\n") == {2, 4}


def test_diagnose_failures_blames_the_right_side():
    from codeforge.pipeline import diagnose_failures
    from codeforge.schemas.validation import TestRun

    setup_bug = TestRun(label="x", failure_text={
        "t::a": "KeyError: 'unknown sku: A'\ntests/test_cf.py:28: in _make_cart\n"
                "shopcart/catalog.py:43: KeyError",
        "t::b": "TypeError: bad\ntests/test_cf.py:30: TypeError"})
    assert diagnose_failures(setup_bug, {"shopcart/pricing.py"},
                             ["tests/test_cf.py"])["verdict"] == "tests"
    ref_bug = TestRun(label="x", failure_text={
        "t::a": "ZeroDivisionError\ntests/test_cf.py:9: in test_a\n"
                "shopcart/pricing.py:77: ZeroDivisionError"})
    assert diagnose_failures(ref_bug, {"shopcart/pricing.py"},
                             ["tests/test_cf.py"])["verdict"] == "reference"
    mismatch = TestRun(label="x", failure_text={
        "t::a": "AssertionError: assert Decimal('1') == Decimal('2')\ntests/test_cf.py:9: "
                "AssertionError"})
    assert diagnose_failures(mismatch, {"shopcart/pricing.py"},
                             ["tests/test_cf.py"])["verdict"] == "unclear"
