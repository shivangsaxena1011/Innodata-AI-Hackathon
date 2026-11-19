"""Repository-level data contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class DirtyPolicy(StrEnum):
    """What to do when a local repository has uncommitted changes."""

    REFUSE = "refuse"          # default: never accept an ambiguous starting state
    USE_HEAD = "use_head"      # ignore working-tree changes, snapshot HEAD exactly
    COMMIT_SNAPSHOT = "commit_snapshot"  # snapshot the working tree as a synthetic commit


class Symbol(BaseModel):
    name: str
    kind: str  # function | class | method | variable | interface
    file: str
    line: int
    signature: str = ""
    parent: str | None = None
    is_test: bool = False


class ImportRef(BaseModel):
    file: str
    module: str
    line: int


class FileSummary(BaseModel):
    path: str
    language: str
    lines: int
    sha256: str
    is_test: bool = False
    syntax_errors: int = 0


class RankedSymbol(BaseModel):
    name: str
    kind: str
    file: str
    line: int
    signature: str
    score: float


class RepositoryMap(BaseModel):
    files: list[FileSummary] = Field(default_factory=list)
    symbols: list[Symbol] = Field(default_factory=list)
    imports: list[ImportRef] = Field(default_factory=list)
    file_rank: dict[str, float] = Field(default_factory=dict)
    ranked_symbols: list[RankedSymbol] = Field(default_factory=list)
    dependency_edges: list[tuple[str, str]] = Field(default_factory=list)
    language_distribution: dict[str, int] = Field(default_factory=dict)
    extension_points: list[str] = Field(default_factory=list)
    rendered: str = ""  # token-budgeted text map for LLM context
    token_budget: int = 0
    cache_key: str = ""


class TestStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class BaselineResult(BaseModel):
    runs: int
    command: list[str]
    passed: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    flaky: list[str] = Field(default_factory=list)
    duration_sec: float = 0.0
    healthy: bool = False
    notes: list[str] = Field(default_factory=list)


class RepositoryProfile(BaseModel):
    repository_name: str
    repository_url: str
    local_path: str
    starting_commit_sha: str
    branch: str | None = None
    primary_language: str
    detected_languages: dict[str, int] = Field(default_factory=dict)
    framework: str | None = None
    runtime_version: str | None = None
    package_manager: str | None = None
    dependency_files: dict[str, str] = Field(default_factory=dict)  # path -> sha256
    test_framework: str | None = None
    test_command: list[str] = Field(default_factory=list)
    build_command: list[str] = Field(default_factory=list)
    test_dirs: list[str] = Field(default_factory=list)
    source_dirs: list[str] = Field(default_factory=list)
    important_files: list[str] = Field(default_factory=list)
    repository_map: RepositoryMap | None = None
    baseline_test_status: BaselineResult | None = None
    adapter: str = "unsupported"
    supported: bool = False
    unsupported_reason: str | None = None
