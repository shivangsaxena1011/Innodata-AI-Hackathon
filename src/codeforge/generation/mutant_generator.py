"""LLM-generated semantic mutants: plausible wrong implementations that a capable agent
might write. Language-agnostic test-quality evidence (complements AST mutation)."""

from __future__ import annotations

import logging

from codeforge.ai import prompt_manager
from codeforge.ai.llm_client import ChatModel
from codeforge.ai.structured_output import StructuredOutputError, generate
from codeforge.generation.context import format_sources
from codeforge.generation.patch_generator import EditError, Worktree, apply_edits
from codeforge.generation.test_generator import spec_for_prompt
from codeforge.schemas.task import MutantResponse, ReferenceSolution, TaskSpec

log = logging.getLogger(__name__)


def generate_semantic_mutants(
    llm: ChatModel, spec: TaskSpec, reference: ReferenceSolution, ref_tree: Worktree,
    count: int = 4,
) -> tuple[list[tuple[str, dict[str, str]]], list[dict]]:
    """Returns [(fault_hypothesis, {path: full mutated content})] and skipped-mutant notes."""
    changed = [c.path for c in reference.changes]
    prompt = prompt_manager.render(
        "mutant_generation",
        count=count,
        spec=spec_for_prompt(spec),
        diff=reference.unified_diff[:20000],
        sources=format_sources(ref_tree.root, changed, overlay=ref_tree.changes),
    )
    try:
        result = generate(llm, MutantResponse, prompt_manager.SYSTEM, prompt, "semantic_mutants")
    except StructuredOutputError as exc:
        return [], [{"error": str(exc)}]
    mutants, skipped = [], []
    for i, m in enumerate(result.value.mutants[:count]):
        tree = ref_tree.fork()
        try:
            touched = apply_edits(tree, m.edits)
        except EditError as exc:
            skipped.append({"index": i, "fault": m.fault_hypothesis, "error": str(exc)[:300]})
            continue
        files = {p: tree.changes[p] for p in set(touched)}
        if all(ref_tree.changes.get(p) == files[p] for p in files):
            skipped.append({"index": i, "fault": m.fault_hypothesis, "error": "no-op mutant"})
            continue
        mutants.append((m.fault_hypothesis, files))
    return mutants, skipped
