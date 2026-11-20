"""Transparent task-validity score. Every component states its rule. This is a heuristic
summary; the executed gates are the actual proof."""

from __future__ import annotations

from codeforge.schemas.validation import (
    GateName,
    GateStatus,
    ScoreComponent,
    ValidationResult,
    ValidityScore,
)


def _gate_score(v: ValidationResult, name: GateName) -> float:
    g = v.gate(name)
    if g is None:
        return 0.0
    return {GateStatus.PASSED: 1.0, GateStatus.WARNING: 0.6, GateStatus.SKIPPED: 0.0,
            GateStatus.UNSUPPORTED: 0.5, GateStatus.FAILED: 0.0}[g.status]


def score(v: ValidationResult, ac_coverage: float, n_criteria: int) -> ValidityScore:
    clarity = min(1.0, n_criteria / 4) * (1.0 if ac_coverage == 1 else ac_coverage)
    mutation = v.mutation_result.score if v.mutation_result and v.mutation_result.score \
        is not None else None
    semantic = v.semantic_mutation_result.score if v.semantic_mutation_result and \
        v.semantic_mutation_result.score is not None else None
    m_parts = [x for x in (mutation, semantic) if x is not None]
    comps = [
        ScoreComponent(name="Requirement clarity", weight=0.10, score=round(clarity, 3),
                       rule="min(1, #criteria/4) x share of criteria traced to >=1 test"),
        ScoreComponent(name="Requirement test coverage", weight=0.10, score=round(ac_coverage, 3),
                       rule="share of acceptance criteria with at least one hidden test"),
        ScoreComponent(name="Repository compatibility", weight=0.10,
                       score=_gate_score(v, GateName.BASELINE),
                       rule="baseline suite healthy and stable in the task environment"),
        ScoreComponent(name="Negative control", weight=0.15,
                       score=_gate_score(v, GateName.NEGATIVE_CONTROL),
                       rule="every hidden feature test fails on the original code"),
        ScoreComponent(name="Reference success", weight=0.15,
                       score=_gate_score(v, GateName.POSITIVE_CONTROL),
                       rule="every hidden feature test passes with the reference"),
        ScoreComponent(name="Regression safety", weight=0.15,
                       score=_gate_score(v, GateName.REGRESSION),
                       rule="all baseline-passing original tests still pass with the reference"),
        ScoreComponent(name="Mutation evidence", weight=0.15,
                       score=round(sum(m_parts) / len(m_parts), 3) if m_parts else 0.0,
                       rule="mean kill rate of diff-scoped AST mutants and semantic mutants"),
        ScoreComponent(name="Reproducibility", weight=0.10,
                       score=_gate_score(v, GateName.STABILITY),
                       rule="identical results across repeated reference runs"),
    ]
    total = round(100 * sum(c.weight * c.score for c in comps), 1)
    return ValidityScore(total=total, components=comps)
