"""Rank and filter feature candidates for clarity, scope, novelty and archetype coverage."""

from __future__ import annotations

from dataclasses import dataclass

from codeforge.discovery.novelty_checker import (
    TaskFingerprint,
    existing_name_conflicts,
    similarity,
)
from codeforge.schemas.task import Difficulty, FeatureCandidate


@dataclass
class RankedCandidate:
    candidate: FeatureCandidate
    score: float
    accepted: bool
    reason: str | None = None


def rank_candidates(
    candidates: list[FeatureCandidate],
    existing_names: set[str],
    accepted: list[TaskFingerprint],
    known_modules: set[str],
    novelty_threshold: float = 0.55,
    limit: int = 3,
) -> list[RankedCandidate]:
    ranked: list[RankedCandidate] = []
    chosen: list[TaskFingerprint] = list(accepted)
    seen_archetypes = {fp.archetype for fp in accepted}

    def base_score(c: FeatureCandidate) -> float:
        s = 0.0
        s += 1.0 if 3 <= len(c.acceptance_criteria) <= 8 else 0.4
        s += 1.0 if 1 <= len(c.affected_modules) <= 3 else 0.3
        s += 0.6 if c.edge_cases else 0.0
        s += {Difficulty.MEDIUM: 0.8, Difficulty.HARD: 0.6, Difficulty.EASY: 0.4}[c.complexity]
        s += 1.0 if c.archetype.value not in seen_archetypes else 0.0
        return s

    for c in sorted(candidates, key=base_score, reverse=True):
        fp = TaskFingerprint.of(c)
        conflicts = existing_name_conflicts(c, existing_names)
        unknown = [m for m in c.affected_modules if m not in known_modules]
        nearest = max((similarity(fp, other) for other in chosen), default=0.0)
        c.novelty_score = round(1 - nearest, 4)
        reason = None
        if conflicts:
            reason = f"contract reuses existing names {conflicts}: feature may already exist"
        elif unknown and len(unknown) == len(c.affected_modules):
            reason = f"affected modules not found in repository: {unknown}"
        elif nearest >= novelty_threshold:
            reason = f"too similar to an existing task (similarity {nearest:.2f})"
        elif len([r for r in ranked if r.accepted]) >= limit:
            reason = "lower ranked than the selected candidates"
        accepted_flag = reason is None
        c.rejection_reason = reason
        ranked.append(RankedCandidate(c, round(base_score(c) + c.novelty_score, 3),
                                      accepted_flag, reason))
        if accepted_flag:
            chosen.append(fp)
            seen_archetypes.add(c.archetype.value)
    return ranked
