"""Repository-aware feature discovery: ask the model for new, behaviourally distinct features
grounded in the ranked repository map, then filter them with static novelty checks."""

from __future__ import annotations

import hashlib
import json
import logging
import re

from codeforge.ai import prompt_manager
from codeforge.ai.llm_client import ChatModel
from codeforge.ai.structured_output import StructuredResult, generate
from codeforge.discovery.feature_ranker import RankedCandidate, rank_candidates
from codeforge.discovery.novelty_checker import TaskFingerprint
from codeforge.schemas.repository import RepositoryProfile
from codeforge.schemas.task import Archetype, DiscoveryResponse

log = logging.getLogger(__name__)

ARCHETYPE_GUIDE = {
    Archetype.BUSINESS_RULE: "a new validation or business rule with thresholds/eligibility",
    Archetype.STATE_MACHINE: "a new state or lifecycle transition with guarded transitions",
    Archetype.QUERY_AGGREGATION: "a new query, filter, report or aggregation over existing data",
    Archetype.CONFIGURATION_POLICY: "a pluggable or configurable policy that changes behaviour",
    Archetype.COMPONENT_INTERACTION: "a feature whose behaviour depends on two existing "
                                     "components interacting",
    Archetype.ERROR_HANDLING: "stricter validation with new typed errors for invalid input",
    Archetype.INTERFACE_EXTENSION: "a new public method/entry point exposing a capability",
}


def existing_public_names(profile: RepositoryProfile) -> set[str]:
    rm = profile.repository_map
    if not rm:
        return set()
    return {s.name for s in rm.symbols if not s.is_test and not s.name.startswith("_")}


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:48].strip("-") or "task"


def discover_features(
    llm: ChatModel,
    profile: RepositoryProfile,
    accepted: list[TaskFingerprint],
    count: int = 6,
    limit: int = 3,
    novelty_threshold: float = 0.55,
    archetypes: list[Archetype] | None = None,
) -> tuple[list[RankedCandidate], StructuredResult[DiscoveryResponse]]:
    rm = profile.repository_map
    archetypes = archetypes or list(Archetype)
    seen = {fp.archetype for fp in accepted}
    order = [a for a in archetypes if a.value not in seen] + \
            [a for a in archetypes if a.value in seen]
    existing = existing_public_names(profile)
    prompt = prompt_manager.render(
        "feature_discovery",
        count=count,
        repo_name=profile.repository_name,
        language=profile.primary_language,
        framework=profile.framework or "none",
        test_framework=profile.test_framework or "unknown",
        source_dirs=", ".join(profile.source_dirs) or ".",
        repo_map=rm.rendered if rm else "(unavailable)",
        extension_points="\n".join(f"- {p}" for p in (rm.extension_points if rm else [])[:15]),
        existing_names=", ".join(sorted(existing)[:300]),
        accepted="\n".join(f"- [{fp.archetype}] {fp.title}" for fp in accepted) or "(none)",
        archetypes="\n".join(f"- {a.value}: {ARCHETYPE_GUIDE[a]}" for a in order),
        archetype_values=", ".join(a.value for a in Archetype),
    )
    result = generate(llm, DiscoveryResponse, prompt_manager.SYSTEM, prompt, "feature_discovery")
    known_modules = {f.path for f in rm.files} if rm else set()
    for c in result.value.candidates:
        c.affected_modules = [m.replace("\\", "/").lstrip("./") for m in c.affected_modules]
        digest = hashlib.sha256(json.dumps(c.model_dump(mode="json"), sort_keys=True)
                                .encode()).hexdigest()[:6]
        c.feature_id = f"{slugify(c.title)}-{digest}"
    ranked = rank_candidates(result.value.candidates, existing, accepted, known_modules,
                             novelty_threshold, limit)
    return ranked, result
