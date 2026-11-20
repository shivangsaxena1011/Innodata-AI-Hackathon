from codeforge.discovery.feature_ranker import rank_candidates
from codeforge.discovery.novelty_checker import TaskFingerprint, diversity_report, similarity
from codeforge.schemas.task import (
    AcceptanceCriterion,
    Archetype,
    FeatureCandidate,
    InterfaceContract,
    TaskSpec,
    TestCaseTrace,
)
from codeforge.validation.independence_checker import check_python_tests
from codeforge.validation.mutation_validator import generate_mutants

SOURCE = '''from decimal import Decimal


def old():
    return 1


def discount(total: Decimal, code: str) -> Decimal:
    if code not in ("SAVE10", "SAVE20"):
        raise ValueError("unknown code")
    if total >= Decimal("50.00") and code == "SAVE20":
        return total * Decimal("0.80")
    return total - Decimal("10")
'''


def test_mutants_only_on_changed_lines_and_compile():
    changed = set(range(8, 14))
    mutants = generate_mutants("pkg/m.py", SOURCE, changed, max_mutants=50)
    assert mutants, "expected mutants"
    ops = {m.operator for m in mutants}
    assert {"compare", "constant", "raise", "return"} <= ops
    for m in mutants:
        compile(m.content, m.file, "exec")
        assert 8 <= m.line <= 13
        assert "def old():\n    return 1" in m.content  # untouched code is preserved
    assert any("'50.00' -> '50.01'" in m.description for m in mutants)


def test_mutant_sampling_is_deterministic():
    a = generate_mutants("m.py", SOURCE, set(range(8, 14)), max_mutants=5, seed=7)
    b = generate_mutants("m.py", SOURCE, set(range(8, 14)), max_mutants=5, seed=7)
    assert [m.mutant_id for m in a] == [m.mutant_id for m in b] and len(a) == 5


def _cand(title, arch, names, reqs, modules=("shopcart/cart.py",)):
    return FeatureCandidate(
        title=title, archetype=arch, problem_statement=title, requirements=reqs,
        acceptance_criteria=["a", "b", "c"], affected_modules=list(modules),
        contract=[InterfaceContract(kind="function", module="shopcart.cart", name=n,
                                    signature=f"def {n}()", behaviour="b") for n in names])


def test_novelty_rejects_near_duplicates_and_existing_names():
    a = _cand("Discount codes with spend threshold", Archetype.BUSINESS_RULE, ["apply_code"],
              ["codes give percent off", "minimum spend threshold applies"])
    b = _cand("Discount codes with minimum spend", Archetype.BUSINESS_RULE, ["apply_code"],
              ["codes give percent off", "minimum spend threshold applies"])
    c = _cand("Partial refunds", Archetype.STATE_MACHINE, ["refund"],
              ["orders can be partially refunded", "refunds move state"],
              ["shopcart/orders.py"])
    d = _cand("Existing thing", Archetype.QUERY_AGGREGATION, ["Cart"], ["x y", "z w"])
    ranked = rank_candidates([a, b, c, d], existing_names={"Cart"}, accepted=[],
                             known_modules={"shopcart/cart.py", "shopcart/orders.py"}, limit=5)
    verdict = {r.candidate.title: r for r in ranked}
    assert verdict["Partial refunds"].accepted
    assert sum(verdict[t].accepted for t in (a.title, b.title)) == 1
    assert "already exist" in verdict["Existing thing"].reason
    fa, fc = TaskFingerprint.of(a), TaskFingerprint.of(c)
    assert similarity(fa, TaskFingerprint.of(b)) > similarity(fa, fc)
    assert diversity_report([fa, fc])["distinct_archetypes"] == 2


SPEC = TaskSpec(
    title="t", archetype=Archetype.BUSINESS_RULE, summary="s", background="b",
    requirements=["r1", "r2"],
    acceptance_criteria=[AcceptanceCriterion(id="AC1", text="a"),
                         AcceptanceCriterion(id="AC2", text="b")],
    contract=[InterfaceContract(kind="function", module="pkg.m", name="discount",
                                signature="def discount()", behaviour="b")])


def test_independence_checker_flags_problems():
    tests = '''import pytest
from pkg.m import discount, _helper, compute_internal


def test_a():
    assert discount() == 1


@pytest.mark.skip
def test_b():
    discount()
'''
    trace = [TestCaseTrace(test_name="test_a", criteria=["AC1"]),
             TestCaseTrace(test_name="test_b", criteria=["AC1"])]
    r = check_python_tests(tests, SPEC, trace, existing_names=set(),
                           reference_new_names={"discount", "compute_internal"})
    joined = " ".join(r.errors)
    assert "compute_internal" in joined          # implementation-only name
    assert "test_b has no assertions" in joined or "skip" in joined
    assert "AC2" in joined                       # untraced criterion
    assert any("_helper" in w for w in r.warnings)
    assert not r.ok


def test_independence_checker_accepts_clean_tests():
    tests = "from pkg.m import discount\n\n\ndef test_a():\n    assert discount() == 1\n\n\n" \
            "def test_b():\n    assert discount() == 2\n"
    trace = [TestCaseTrace(test_name="test_a", criteria=["AC1"]),
             TestCaseTrace(test_name="test_b", criteria=["AC2"])]
    assert check_python_tests(tests, SPEC, trace, set(), {"discount"}).ok


STATE_SRC = '''from enum import Enum


class S(Enum):
    A = "a"
    B = "b"
    C = "c"


ALLOWED = {S.A: {S.B, S.C}, S.B: {S.C}}


def advance(order, inv):
    inv.release(order)
    order.count += 1
    return S.B
'''


def test_structural_mutants_for_state_machines():
    mutants = generate_mutants("m.py", STATE_SRC, set(range(10, 17)), max_mutants=50)
    ops = {m.operator for m in mutants}
    assert {"collection", "enum_swap", "statement", "arithmetic"} <= ops
    for m in mutants:
        compile(m.content, "m.py", "exec")
    assert any("remove element S.B" in m.description for m in mutants)
    assert any("delete call inv.release" in m.description for m in mutants)
