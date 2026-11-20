"""A hand-written task used ONLY to test CodeForge's packaging and Harbor integration.
It is not generated output and is never shown as such."""

from codeforge.schemas.task import (
    AcceptanceCriterion,
    Archetype,
    FileChange,
    GeneratedTask,
    InterfaceContract,
    ReferenceSolution,
    TaskSpec,
    TestCaseTrace,
    TestFile,
)

MONEY_ADDITION = '''

def clamp_non_negative(amount: Decimal) -> Decimal:
    """Return `amount`, or 0.00 when it is negative."""
    return to_money(amount) if amount > 0 else Decimal("0.00")
'''

TEST_SOURCE = '''from decimal import Decimal

from shopcart.money import clamp_non_negative


def test_positive_amount_unchanged():
    assert clamp_non_negative(Decimal("3.456")) == Decimal("3.46")


def test_negative_amount_becomes_zero():
    assert clamp_non_negative(Decimal("-1")) == Decimal("0.00")


def test_zero_stays_zero():
    assert clamp_non_negative(Decimal("0")) == Decimal("0.00")
'''


def build(original_money: str, sha: str, url: str) -> GeneratedTask:
    new_money = original_money + MONEY_ADDITION
    spec = TaskSpec(
        task_id="fixture-clamp-non-negative", title="Clamp negative amounts to zero",
        archetype=Archetype.BUSINESS_RULE, summary="Add clamp_non_negative to money helpers.",
        background="Refund maths must never produce negative totals.",
        requirements=["Add clamp_non_negative(amount)", "Negative amounts become 0.00"],
        acceptance_criteria=[AcceptanceCriterion(id="AC1", text="Positive values are rounded"),
                             AcceptanceCriterion(id="AC2", text="Negative values become 0.00")],
        contract=[InterfaceContract(kind="function", module="shopcart.money",
                                    name="clamp_non_negative",
                                    signature="def clamp_non_negative(amount: Decimal) -> Decimal",
                                    behaviour="rounded amount, or 0.00 when negative")],
        relevant_files=["shopcart/money.py"],
    )
    ref = ReferenceSolution(explanation="adds clamp_non_negative",
                            changes=[FileChange(path="shopcart/money.py", action="modify",
                                                content=new_money)],
                            unified_diff="")
    return GeneratedTask(
        task_id=spec.task_id, title=spec.title, archetype=spec.archetype,
        starting_commit_sha=sha, repository_url=url, spec=spec,
        instruction="# Clamp negative amounts to zero\n\nAdd `clamp_non_negative`.\n",
        reference=ref,
        feature_test_files=[TestFile(path="tests/test_codeforge_fixture.py", content=TEST_SOURCE)],
        traceability=[TestCaseTrace(test_name="test_positive_amount_unchanged", criteria=["AC1"]),
                      TestCaseTrace(test_name="test_negative_amount_becomes_zero",
                                    criteria=["AC2"])],
    )
