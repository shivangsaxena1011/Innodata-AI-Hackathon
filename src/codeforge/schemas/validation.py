"""Validation evidence contracts. Values here come only from real executions."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, Field


class GateName(StrEnum):
    BASELINE = "baseline"
    NEGATIVE_CONTROL = "negative_control"
    POSITIVE_CONTROL = "positive_control"
    REGRESSION = "regression"
    MUTATION = "mutation"
    SEMANTIC_MUTANTS = "semantic_mutants"
    STABILITY = "stability"
    INDEPENDENCE = "independence"
    LEAKAGE = "leakage"
    HARBOR_LINT = "harbor_lint"
    HARBOR_ORACLE = "harbor_oracle"
    HARBOR_NOP = "harbor_nop"


class GateStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"
    UNSUPPORTED = "unsupported"


class TestRun(BaseModel):
    __test__: ClassVar[bool] = False  # not a pytest test class

    label: str
    command: list[str] = Field(default_factory=list)
    passed: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    exit_code: int | None = None
    duration_sec: float = 0.0
    log_path: str | None = None
    timed_out: bool = False
    failure_text: dict[str, str] = Field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.passed) + len(self.failed) + len(self.errors)


class GateResult(BaseModel):
    gate: GateName
    status: GateStatus
    summary: str
    details: dict = Field(default_factory=dict)
    log_paths: list[str] = Field(default_factory=list)


class MutantOutcome(BaseModel):
    mutant_id: str
    operator: str
    file: str
    line: int
    description: str
    killed: bool
    killed_by: list[str] = Field(default_factory=list)
    diff: str = ""


class MutationResult(BaseModel):
    engine: str
    total: int = 0
    killed: int = 0
    survived: int = 0
    errors: int = 0
    score: float | None = None
    outcomes: list[MutantOutcome] = Field(default_factory=list)
    supported: bool = True
    note: str = ""


class ScoreComponent(BaseModel):
    name: str
    weight: float
    score: float
    rule: str


class ValidityScore(BaseModel):
    total: float
    components: list[ScoreComponent]
    disclaimer: str = (
        "Heuristic quality score. Proof of validity comes from the executed gates, not this number."
    )


class ValidityStatus(StrEnum):
    VALID = "valid"
    REJECTED = "rejected"


class ValidationResult(BaseModel):
    task_id: str
    baseline_result: TestRun | None = None
    feature_negative_control: TestRun | None = None
    reference_positive_control: TestRun | None = None
    regression_result: TestRun | None = None
    mutation_result: MutationResult | None = None
    semantic_mutation_result: MutationResult | None = None
    coverage_result: dict | None = None
    harbor_validation: dict = Field(default_factory=dict)
    gates: list[GateResult] = Field(default_factory=list)
    score: ValidityScore | None = None
    final_validity_status: ValidityStatus = ValidityStatus.REJECTED
    rejection_reasons: list[str] = Field(default_factory=list)
    attempts: list[dict] = Field(default_factory=list)
    validation_logs: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def gate(self, name: GateName) -> GateResult | None:
        return next((g for g in self.gates if g.gate == name), None)
