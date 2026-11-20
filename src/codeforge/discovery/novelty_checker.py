"""Variation and duplicate detection.

Two tasks count as duplicates when they exercise the same behaviour, not when they share
words. Similarity combines (a) requirement-text overlap, (b) interface-contract overlap,
(c) the same behaviour archetype and (d) overlap of the modules they touch. A candidate is
also rejected when its contract reuses a name that already exists in the repository,
because that usually means the "new" feature already exists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from codeforge.schemas.task import FeatureCandidate

_STOP_WORDS = (
    "a an the and or of to in on for with by is are be it this that as at from into must "
    "should shall will can new existing when if then than each per not no only also all any "
    "returns return value values given"
)
_STOP = frozenset(_STOP_WORDS.split())


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z][a-z0-9]+", text.lower())
    return {w[:-1] if w.endswith("s") and len(w) > 4 else w for w in words if w not in _STOP}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


@dataclass(frozen=True)
class TaskFingerprint:
    title: str
    archetype: str
    text_tokens: frozenset[str]
    contract_names: frozenset[str]
    modules: frozenset[str]

    @classmethod
    def of(cls, c: FeatureCandidate) -> TaskFingerprint:
        text = " ".join([c.title, c.problem_statement, *c.requirements, *c.acceptance_criteria])
        return cls(
            c.title, c.archetype.value, frozenset(_tokens(text)),
            frozenset(x.name.split(".")[-1].lower() for x in c.contract),
            frozenset(m.lower() for m in c.affected_modules),
        )

    def to_dict(self) -> dict:
        return {"title": self.title, "archetype": self.archetype,
                "text_tokens": sorted(self.text_tokens),
                "contract_names": sorted(self.contract_names), "modules": sorted(self.modules)}

    @classmethod
    def from_dict(cls, d: dict) -> TaskFingerprint:
        return cls(d["title"], d["archetype"], frozenset(d["text_tokens"]),
                   frozenset(d["contract_names"]), frozenset(d["modules"]))


def similarity(a: TaskFingerprint, b: TaskFingerprint) -> float:
    text = jaccard(set(a.text_tokens), set(b.text_tokens))
    contract = jaccard(set(a.contract_names), set(b.contract_names))
    modules = jaccard(set(a.modules), set(b.modules))
    same_arch = 1.0 if a.archetype == b.archetype else 0.0
    return round(0.45 * text + 0.25 * contract + 0.2 * same_arch + 0.1 * modules, 4)


def existing_name_conflicts(c: FeatureCandidate, existing: set[str]) -> list[str]:
    conflicts = []
    for item in c.contract:
        leaf = item.name.split(".")[-1]
        if item.kind in ("function", "class", "constant", "exception") and leaf in existing:
            conflicts.append(leaf)
    return conflicts


def diversity_report(fps: list[TaskFingerprint]) -> dict:
    pairs = []
    for i in range(len(fps)):
        for j in range(i + 1, len(fps)):
            pairs.append({"a": fps[i].title, "b": fps[j].title,
                          "similarity": similarity(fps[i], fps[j])})
    archetypes = sorted({f.archetype for f in fps})
    mean = sum(p["similarity"] for p in pairs) / len(pairs) if pairs else 0.0
    return {
        "tasks": len(fps), "distinct_archetypes": len(archetypes), "archetypes": archetypes,
        "mean_pairwise_similarity": round(mean, 4),
        "max_pairwise_similarity": max((p["similarity"] for p in pairs), default=0.0),
        "diversity_score": round(1 - mean, 4) if pairs else None, "pairs": pairs,
    }
