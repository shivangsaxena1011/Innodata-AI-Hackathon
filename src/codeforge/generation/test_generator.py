"""Independent test generation: tests are written from the specification only, in a separate
model call that never sees the reference implementation."""

from __future__ import annotations

from pathlib import Path

from codeforge.adapters.languages.base import LanguageAdapter
from codeforge.ai import prompt_manager
from codeforge.ai.llm_client import ChatModel
from codeforge.ai.structured_output import StructuredResult, generate
from codeforge.generation.context import example_test, format_sources, relevant_files
from codeforge.schemas.repository import RepositoryProfile
from codeforge.schemas.task import TaskSpec, TestBundleResponse
from codeforge.utils.fs import safe_relpath


def spec_for_prompt(spec: TaskSpec) -> str:
    return spec.model_dump_json(indent=2, exclude={"task_id", "relevant_files",
                                                   "estimated_minutes"})


def generate_tests(
    llm: ChatModel,
    profile: RepositoryProfile,
    root: Path,
    spec: TaskSpec,
    adapter: LanguageAdapter,
    repair_note: str = "",
) -> StructuredResult[TestBundleResponse]:
    test_path = adapter.feature_test_path(profile, spec.task_id)
    # Tests must build objects with the EXISTING API, so they see the relevant files plus the
    # modules those files depend on, and the fixtures existing tests use.
    files = relevant_files(profile, spec.relevant_files, limit=8)
    prompt = prompt_manager.render(
        "test_generation",
        repo_name=profile.repository_name,
        language=profile.primary_language,
        test_framework=profile.test_framework or "unknown",
        style_hint=adapter.test_style_hint(profile),
        spec=spec_for_prompt(spec),
        repo_map=profile.repository_map.rendered if profile.repository_map else "",
        sources=format_sources(root, files),
        example_test=example_test(root, profile),
        test_path=test_path,
        repair_note=f"\n## Fix required\n{repair_note}" if repair_note else "",
    )
    purpose = "feature_tests" if not repair_note else "feature_tests_repair"
    result = generate(llm, TestBundleResponse, prompt_manager.SYSTEM, prompt, purpose)
    # Force the single hidden test file onto the adapter's path.
    files = result.value.files
    merged = "\n\n".join(f.content for f in files) if len(files) > 1 else files[0].content
    files[:] = [type(files[0])(path=safe_relpath(test_path), content=merged)]
    return result
