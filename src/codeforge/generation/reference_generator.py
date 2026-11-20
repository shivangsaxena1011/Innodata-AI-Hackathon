"""Reference implementation generation, applied to a throwaway in-memory worktree."""

from __future__ import annotations

from pathlib import Path

from codeforge.ai import prompt_manager
from codeforge.ai.llm_client import ChatModel
from codeforge.ai.structured_output import generate
from codeforge.generation.context import format_sources, relevant_files
from codeforge.generation.patch_generator import (
    EditError,
    Worktree,
    apply_edits,
    to_file_changes,
    unified_diff,
)
from codeforge.generation.test_generator import spec_for_prompt
from codeforge.schemas.repository import RepositoryProfile
from codeforge.schemas.task import ReferenceResponse, ReferenceSolution, TaskSpec


class ReferenceError_(RuntimeError):
    pass


def generate_reference(
    llm: ChatModel,
    profile: RepositoryProfile,
    root: Path,
    spec: TaskSpec,
    repair_note: str = "",
    max_edit_retries: int = 1,
) -> tuple[ReferenceSolution, Worktree, list[dict]]:
    """Returns the reference solution, the worktree holding it, and attempt records."""
    attempts: list[dict] = []
    note = repair_note
    for _attempt in range(max_edit_retries + 1):
        tree = Worktree(root)
        prompt = prompt_manager.render(
            "reference_generation",
            repo_name=profile.repository_name,
            language=profile.primary_language,
            commit=profile.starting_commit_sha,
            spec=spec_for_prompt(spec),
            repo_map=profile.repository_map.rendered if profile.repository_map else "",
            sources=format_sources(root, relevant_files(profile, spec.relevant_files, 8)),
            repair_note=f"\n## Fix required\n{note}" if note else "",
        )
        purpose = "reference" if not note else "reference_repair"
        result = generate(llm, ReferenceResponse, prompt_manager.SYSTEM, prompt, purpose)
        try:
            apply_edits(tree, result.value.edits)
        except EditError as exc:
            attempts.append({"stage": "apply_edits", "ok": False, "error": str(exc)})
            note = (f"{repair_note}\nYour previous edits could not be applied: {exc}. Copy "
                    f"SEARCH text exactly from the current file content.").strip()
            continue
        changes = to_file_changes(tree)
        if not changes:
            attempts.append({"stage": "apply_edits", "ok": False, "error": "no changes"})
            note = f"{repair_note}\nYour previous edits changed nothing.".strip()
            continue
        attempts.append({"stage": "apply_edits", "ok": True, "files": [c.path for c in changes]})
        solution = ReferenceSolution(explanation=result.value.explanation, changes=changes,
                                     unified_diff=unified_diff(tree, changes))
        return solution, tree, attempts
    raise ReferenceError_(f"reference edits could not be applied: {attempts[-1]}")
