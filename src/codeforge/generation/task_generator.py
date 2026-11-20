"""Generate the full task specification (requirements, acceptance criteria, contract)."""

from __future__ import annotations

import json
from pathlib import Path

from codeforge.ai import prompt_manager
from codeforge.ai.llm_client import ChatModel
from codeforge.ai.structured_output import StructuredResult, generate
from codeforge.generation.context import format_sources, relevant_files
from codeforge.schemas.repository import RepositoryProfile
from codeforge.schemas.task import FeatureCandidate, TaskSpec


def generate_spec(
    llm: ChatModel, profile: RepositoryProfile, root: Path, candidate: FeatureCandidate
) -> StructuredResult[TaskSpec]:
    files = relevant_files(profile, candidate.affected_modules)
    prompt = prompt_manager.render(
        "task_generation",
        repo_name=profile.repository_name,
        language=profile.primary_language,
        test_framework=profile.test_framework or "unknown",
        commit=profile.starting_commit_sha,
        candidate=json.dumps(candidate.model_dump(mode="json", exclude={"novelty_score",
                             "rejection_reason"}), indent=2),
        sources=format_sources(root, files),
        archetype=candidate.archetype.value,
    )
    result = generate(llm, TaskSpec, prompt_manager.SYSTEM, prompt, "task_spec")
    spec = result.value
    spec.task_id = candidate.feature_id
    spec.archetype = candidate.archetype
    if not spec.relevant_files:
        spec.relevant_files = files
    return result


def render_instruction(spec: TaskSpec, profile: RepositoryProfile) -> str:
    """Agent-visible instruction. It contains the contract and requirements, never tests,
    test paths or reference code."""
    lines = [f"# {spec.title}", "", spec.summary, "", "## Background", spec.background, "",
             "## Requirements"]
    lines += [f"{i}. {r}" for i, r in enumerate(spec.requirements, 1)]
    lines += ["", "## Acceptance criteria"]
    lines += [f"- **{a.id}**: {a.text}" for a in spec.acceptance_criteria]
    lines += ["", "## Interface contract",
              "Implement exactly these public names; automated checks use them.", ""]
    for c in spec.contract:
        lines.append(f"- `{c.module}` → **{c.kind}** `{c.signature}`  ")
        lines.append(f"  {c.behaviour}")
    if spec.edge_cases:
        lines += ["", "## Edge cases"] + [f"- {e}" for e in spec.edge_cases]
    if spec.error_handling:
        lines += ["", "## Error handling"] + [f"- {e}" for e in spec.error_handling]
    if spec.interactions:
        lines += ["", "## Interaction with existing behaviour"] + [f"- {e}" for e in
                                                                 spec.interactions]
    constraints = list(dict.fromkeys(spec.constraints + [
        "Do not modify or delete existing tests.",
        "Do not add new third-party dependencies.",
        "Keep all existing behaviour working.",
    ]))
    lines += ["", "## Constraints"] + [f"- {c}" for c in constraints]
    if spec.out_of_scope:
        lines += ["", "## Out of scope"] + [f"- {c}" for c in spec.out_of_scope]
    lines += ["", "## Environment",
              f"The repository ({profile.primary_language}) is in the current working "
              f"directory. You may run the existing test suite to check your work."]
    return "\n".join(lines) + "\n"
