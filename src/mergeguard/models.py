"""Core data models for MergeGuard.

All models use Pydantic V2 for validation, serialization, and type safety.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────


class ConflictSeverity(str, Enum):
    CRITICAL = "critical"  # Will definitely break if both merge
    WARNING = "warning"  # Likely to cause issues, needs human review
    INFO = "info"  # Overlap detected but probably fine


class ConflictType(str, Enum):
    HARD = "hard"  # Same lines modified differently
    INTERFACE = "interface"  # Signature changed, callers not updated
    BEHAVIORAL = "behavioral"  # Same logic modified incompatibly
    DUPLICATION = "duplication"  # Same work done in two PRs
    TRANSITIVE = "transitive"  # Conflict through dependency chain
    REGRESSION = "regression"  # Reverts a recent deliberate change


class SymbolType(str, Enum):
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    VARIABLE = "variable"
    CONSTANT = "constant"
    EXPORT = "export"
    IMPORT = "import"
    TYPE_ALIAS = "type_alias"
    INTERFACE = "interface"  # TypeScript/Go interfaces
    ENDPOINT = "endpoint"  # API route definitions


class FileChangeStatus(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    REMOVED = "removed"
    RENAMED = "renamed"


class AIAttribution(str, Enum):
    HUMAN = "human"
    AI_CONFIRMED = "ai_confirmed"  # Agent Trace or commit metadata
    AI_SUSPECTED = "ai_suspected"  # Heuristic detection
    UNKNOWN = "unknown"


# ──────────────────────────────────────────────
# Symbol & File Models
# ──────────────────────────────────────────────


class Symbol(BaseModel):
    """A named code entity (function, class, method, etc.)."""

    name: str
    symbol_type: SymbolType
    file_path: str
    start_line: int
    end_line: int
    signature: str | None = None  # e.g., "def process(items: list, limit: int = 10) -> dict"
    parent: str | None = None  # e.g., class name for methods
    dependencies: list[str] = Field(default_factory=list)  # symbols this one calls/references


class ChangedFile(BaseModel):
    """A file that was modified in a PR."""

    path: str
    status: FileChangeStatus
    additions: int = 0
    deletions: int = 0
    patch: str | None = None  # Raw unified diff patch
    previous_path: str | None = None  # For renames


class ChangedSymbol(BaseModel):
    """A symbol that was modified in a specific PR."""

    symbol: Symbol
    change_type: str  # "modified_body", "modified_signature", "added", "removed"
    diff_lines: tuple[int, int]  # Line range of the change within the file
    raw_diff: str | None = None  # The actual diff hunk for this symbol


# ──────────────────────────────────────────────
# PR Model
# ──────────────────────────────────────────────


class PRInfo(BaseModel):
    """Representation of a pull request with its analysis data."""

    number: int
    title: str
    author: str
    base_branch: str
    head_branch: str
    head_sha: str
    created_at: datetime
    updated_at: datetime
    labels: list[str] = Field(default_factory=list)
    description: str = ""

    # Populated by analysis
    changed_files: list[ChangedFile] = Field(default_factory=list)
    changed_symbols: list[ChangedSymbol] = Field(default_factory=list)
    ai_attribution: AIAttribution = AIAttribution.UNKNOWN

    @property
    def file_paths(self) -> set[str]:
        return {f.path for f in self.changed_files}

    @property
    def symbol_names(self) -> set[str]:
        return {s.symbol.name for s in self.changed_symbols}


# ──────────────────────────────────────────────
# Conflict Models
# ──────────────────────────────────────────────


class Conflict(BaseModel):
    """A detected conflict between two PRs."""

    conflict_type: ConflictType
    severity: ConflictSeverity
    source_pr: int  # The PR being analyzed
    target_pr: int  # The conflicting PR
    file_path: str
    symbol_name: str | None = None  # None for file-level conflicts
    description: str  # Human-readable explanation
    recommendation: str  # Suggested action
    source_lines: tuple[int, int] | None = None
    target_lines: tuple[int, int] | None = None


class ConflictReport(BaseModel):
    """Full analysis report for a single PR."""

    pr: PRInfo
    conflicts: list[Conflict] = Field(default_factory=list)
    risk_score: float = 0.0  # 0-100
    risk_factors: dict[str, float] = Field(default_factory=dict)
    no_conflict_prs: list[int] = Field(default_factory=list)
    analysis_duration_ms: int = 0
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))

    @property
    def has_critical(self) -> bool:
        return any(c.severity == ConflictSeverity.CRITICAL for c in self.conflicts)

    @property
    def conflict_count_by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for c in self.conflicts:
            counts[c.severity.value] = counts.get(c.severity.value, 0) + 1
        return counts


# ──────────────────────────────────────────────
# Decisions Log Models (V1)
# ──────────────────────────────────────────────


class DecisionType(str, Enum):
    REMOVAL = "removal"  # Something was deliberately removed
    ADDITION = "addition"  # New pattern/module introduced
    MIGRATION = "migration"  # Pattern A replaced with pattern B
    REFACTOR = "refactor"  # Code moved/restructured
    PATTERN_CHANGE = "pattern_change"  # Coding convention change


class Decision(BaseModel):
    """A significant code decision extracted from a merged PR."""

    decision_type: DecisionType
    entity: str  # What was changed (function name, pattern, etc.)
    file_path: str | None = None
    description: str
    pr_number: int
    merged_at: datetime
    author: str


class DecisionsEntry(BaseModel):
    """Record of decisions from a single merged PR."""

    pr_number: int
    title: str
    merged_at: datetime
    author: str
    decisions: list[Decision] = Field(default_factory=list)


# ──────────────────────────────────────────────
# Configuration Models
# ──────────────────────────────────────────────


class GuardrailRule(BaseModel):
    """A single guardrail rule from .mergeguard.yml."""

    name: str
    pattern: str | None = None  # File glob pattern
    cannot_import_from: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)
    max_cyclomatic_complexity: int | None = None
    max_function_lines: int | None = None
    when: str | None = None  # Condition, e.g., "ai_authored"
    max_files_changed: int | None = None
    max_lines_changed: int | None = None
    message: str = ""


class MergeGuardConfig(BaseModel):
    """Configuration loaded from .mergeguard.yml."""

    risk_threshold: int = 50  # Only comment if risk > threshold
    check_regressions: bool = True
    max_open_prs: int = 30  # Performance limit
    decisions_log_depth: int = 50  # How many merged PRs to track
    llm_enabled: bool = False
    llm_model: str = "claude-sonnet-4-20250514"
    ignored_paths: list[str] = Field(
        default_factory=lambda: [
            "*.lock",
            "*.min.js",
            "*.min.css",
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "poetry.lock",
        ]
    )
    rules: list[GuardrailRule] = Field(default_factory=list)
