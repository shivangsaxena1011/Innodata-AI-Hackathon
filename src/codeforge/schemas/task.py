"""Task-level data contracts. Every LLM response is parsed into one of these models."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class Archetype(StrEnum):
    """Behaviour families. Variation is enforced across these, not across wording."""

    BUSINESS_RULE = "business_rule"
    STATE_MACHINE = "state_machine"
    QUERY_AGGREGATION = "query_aggregation"
    CONFIGURATION_POLICY = "configuration_policy"
    COMPONENT_INTERACTION = "component_interaction"
    ERROR_HANDLING = "error_handling"
    INTERFACE_EXTENSION = "interface_extension"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class InterfaceContract(BaseModel):
    """The observable surface hidden tests are allowed to touch."""

    kind: str = Field(description="function | method | class | constant | exception")
    module: str = Field(description="importable module path, e.g. shopcart.pricing")
    name: str
    signature: str
    behaviour: str

    @field_validator("name")
    @classmethod
    def _identifier(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", v):
            raise ValueError(f"contract name must be an identifier: {v!r}")
        return v


class FeatureCandidate(BaseModel):
    feature_id: str = ""
    title: str
    archetype: Archetype
    problem_statement: str
    requirements: list[str] = Field(min_length=2)
    acceptance_criteria: list[str] = Field(min_length=2)
    complexity: Difficulty = Difficulty.MEDIUM
    affected_modules: list[str] = Field(min_length=1)
    existing_behaviour: str = ""
    edge_cases: list[str] = Field(default_factory=list)
    contract: list[InterfaceContract] = Field(min_length=1)
    novelty_score: float = 0.0
    rejection_reason: str | None = None


class DiscoveryResponse(BaseModel):
    candidates: list[FeatureCandidate] = Field(min_length=1)


class AcceptanceCriterion(BaseModel):
    id: str
    text: str

    @field_validator("id")
    @classmethod
    def _ac_id(cls, v: str) -> str:
        if not re.fullmatch(r"AC\d{1,2}", v):
            raise ValueError("acceptance criterion ids must look like AC1, AC2, ...")
        return v


class TaskSpec(BaseModel):
    task_id: str = ""
    title: str
    archetype: Archetype
    summary: str
    background: str
    requirements: list[str] = Field(min_length=2)
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=2)
    contract: list[InterfaceContract] = Field(min_length=1)
    edge_cases: list[str] = Field(default_factory=list)
    error_handling: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    interactions: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    difficulty: Difficulty = Difficulty.MEDIUM
    estimated_minutes: int = 30
    relevant_files: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ac(self) -> TaskSpec:
        ids = [a.id for a in self.acceptance_criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("acceptance criterion ids must be unique")
        return self


class FileEdit(BaseModel):
    """An Aider-style SEARCH/REPLACE edit. Empty `search` with a new path creates a file."""

    path: str
    search: str = ""
    replace: str


class ReferenceResponse(BaseModel):
    explanation: str
    edits: list[FileEdit] = Field(min_length=1)


class TestCaseTrace(BaseModel):
    test_name: str
    criteria: list[str] = Field(min_length=1)


class TestFile(BaseModel):
    path: str
    content: str


class TestBundleResponse(BaseModel):
    files: list[TestFile] = Field(min_length=1)
    traceability: list[TestCaseTrace] = Field(min_length=1)


class MutantProposal(BaseModel):
    fault_hypothesis: str
    edits: list[FileEdit] = Field(min_length=1)


class MutantResponse(BaseModel):
    mutants: list[MutantProposal] = Field(min_length=1)


class FileChange(BaseModel):
    path: str
    action: str  # create | modify
    before_sha256: str | None = None
    content: str


class ReferenceSolution(BaseModel):
    explanation: str
    changes: list[FileChange]
    unified_diff: str


class GeneratedTask(BaseModel):
    task_id: str
    title: str
    archetype: Archetype
    starting_commit_sha: str
    repository_url: str
    spec: TaskSpec
    instruction: str = ""
    reference: ReferenceSolution
    feature_test_files: list[TestFile]
    feature_test_ids: list[str] = Field(default_factory=list)
    regression_test_ids: list[str] = Field(default_factory=list)
    traceability: list[TestCaseTrace] = Field(default_factory=list)
    generation_metadata: dict = Field(default_factory=dict)
