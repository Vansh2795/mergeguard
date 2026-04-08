"""Core data models for MergeGuard.

All models use Pydantic V2 for validation, serialization, and type safety.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────


class ConflictSeverity(StrEnum):
    CRITICAL = "critical"  # Will definitely break if both merge
    WARNING = "warning"  # Likely to cause issues, needs human review
    INFO = "info"  # Overlap detected but probably fine


class ConflictType(StrEnum):
    HARD = "hard"  # Same lines modified differently
    INTERFACE = "interface"  # Signature changed, callers not updated
    BEHAVIORAL = "behavioral"  # Same logic modified incompatibly
    DUPLICATION = "duplication"  # Same work done in two PRs
    TRANSITIVE = "transitive"  # Conflict through dependency chain
    REGRESSION = "regression"  # Reverts a recent deliberate change
    GUARDRAIL = "guardrail"  # Rule violation from .mergeguard.yml
    SECRET = "secret"  # Accidentally committed secret/credential


class SymbolType(StrEnum):
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


class FileChangeStatus(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    REMOVED = "removed"
    RENAMED = "renamed"


class PRState(StrEnum):
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"


class AIAttribution(StrEnum):
    HUMAN = "human"
    AI_CONFIRMED = "ai_confirmed"  # Agent Trace or commit metadata
    AI_SUSPECTED = "ai_suspected"  # Heuristic detection
    UNKNOWN = "unknown"


class PolicyConditionOp(StrEnum):
    GTE = "gte"
    LTE = "lte"
    EQ = "eq"
    GT = "gt"
    LT = "lt"
    CONTAINS = "contains"  # set/list membership
    MATCHES = "matches"  # glob pattern on file paths


class PolicyActionType(StrEnum):
    BLOCK_MERGE = "block_merge"
    REQUIRE_REVIEWERS = "require_reviewers"
    ADD_LABELS = "add_labels"
    NOTIFY_SLACK = "notify_slack"
    NOTIFY_TEAMS = "notify_teams"
    POST_COMMENT = "post_comment"
    SET_STATUS = "set_status"


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
    is_fork: bool = False
    created_at: datetime
    updated_at: datetime
    state: PRState = PRState.OPEN
    merged_at: datetime | None = None
    closed_at: datetime | None = None
    labels: list[str] = Field(default_factory=list)
    description: str = ""

    # Populated by analysis
    changed_files: list[ChangedFile] = Field(default_factory=list)
    changed_symbols: list[ChangedSymbol] = Field(default_factory=list)
    ai_attribution: AIAttribution = AIAttribution.UNKNOWN
    skipped_files: list[str] = Field(default_factory=list)

    @property
    def file_paths(self) -> set[str]:
        return {f.path for f in self.changed_files}

    @property
    def symbol_names(self) -> set[str]:
        return {s.symbol.name for s in self.changed_symbols}


class StackGroup(BaseModel):
    """A group of stacked PRs in dependency order (base-first)."""

    group_id: str  # e.g., "chain-feature/auth" or "label-auth-refactor"
    pr_numbers: list[int]  # Ordered: root → tip
    base_branch: str  # Ultimate target (e.g., "main")
    detection_method: str  # "branch_chain" | "labels" | "graphite"
    is_complete: bool = True  # False if middle PRs are missing


# ──────────────────────────────────────────────
# Blast Radius Models
# ──────────────────────────────────────────────


class BlastRadiusNode(BaseModel):
    """A node in the blast radius graph (one per PR)."""

    pr_number: int
    title: str
    author: str
    risk_score: float
    conflict_count: int
    direct_blast: int  # PRs directly conflicting
    transitive_blast: int  # PRs reachable through conflict chains
    severity_max: str  # Highest severity among conflicts
    stack_group: str | None = None
    ai_authored: bool = False
    files_changed: list[str] = Field(default_factory=list)


class BlastRadiusEdge(BaseModel):
    """An edge in the blast radius graph (conflict between two PRs)."""

    source_pr: int
    target_pr: int
    conflict_count: int
    severity_max: str
    conflict_types: list[str]
    is_intra_stack: bool = False
    files: list[str] = Field(default_factory=list)


class BlastRadiusData(BaseModel):
    """Complete blast radius graph data."""

    nodes: list[BlastRadiusNode]
    edges: list[BlastRadiusEdge]
    file_edges: list[dict[str, Any]] = Field(default_factory=list)
    stack_groups: list[dict[str, Any]] = Field(default_factory=list)
    repo: str
    generated_at: datetime


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
    fix_suggestion: str | None = None  # Template or LLM-generated fix suggestion
    cross_file: bool = False  # True if conflict spans different files
    source_diff_preview: str | None = None  # Code preview from source PR
    target_diff_preview: str | None = None  # Code preview from target PR
    owners: list[str] = Field(default_factory=list)  # Code owners for conflicting files
    is_intra_stack: bool = False  # True if both PRs are in the same stack
    original_severity: ConflictSeverity | None = None  # Preserved when demoted


class ConflictReport(BaseModel):
    """Full analysis report for a single PR."""

    pr: PRInfo
    conflicts: list[Conflict] = Field(default_factory=list)
    risk_score: float = 0.0  # 0-100
    risk_factors: dict[str, float] = Field(default_factory=dict)
    no_conflict_prs: list[int] = Field(default_factory=list)
    affected_teams: list[str] = Field(default_factory=list)  # All teams with conflicts
    analysis_duration_ms: int = 0
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stack_group: str | None = None  # StackGroup.group_id if PR is in a stack
    stack_position: int | None = None  # 1-indexed position within the stack
    stack_pr_numbers: list[int] = Field(default_factory=list)  # Full stack in order

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


class DecisionType(StrEnum):
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


class ServerConfig(BaseModel):
    """Configuration for the webhook server."""

    port: int = 8000
    host: str = "0.0.0.0"
    workers: int = 1
    analysis_timeout: int = 300  # seconds
    queue_backend: str = "asyncio"  # "asyncio" | "redis"


class CodeownersConfig(BaseModel):
    """Configuration for CODEOWNERS-aware routing."""

    enabled: bool = True
    path: str | None = None  # Auto-detect if None
    team_channels: dict[str, str] = Field(default_factory=dict)  # @team → Slack channel/webhook


class MergeQueueConfig(BaseModel):
    """Configuration for merge queue integration."""

    enabled: bool = False
    block_on_conflicts: bool = True
    block_severity: str = "critical"  # "critical" | "warning" | "info"
    status_context: str = "mergeguard/cross-pr-analysis"
    priority_labels: dict[str, int] = Field(
        default_factory=lambda: {
            "merge-priority:high": 100,
            "merge-priority:low": -100,
        }
    )
    auto_recheck_on_close: bool = True


class StackedPRConfig(BaseModel):
    """Configuration for stacked PR detection."""

    enabled: bool = True
    detection: list[str] = Field(default_factory=lambda: ["branch_chain", "labels"])
    demote_severity: bool = True
    label_pattern: str = "stack:"


class PolicyCondition(BaseModel):
    """A single condition in a policy rule."""

    field: str  # "risk_score", "conflict_count", "has_severity", etc.
    operator: PolicyConditionOp = PolicyConditionOp.GTE
    value: Any


class PolicyAction(BaseModel):
    """An action to execute when a policy rule matches."""

    action: PolicyActionType
    reviewers: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    webhook_url: str = ""
    message: str = ""
    status_state: str = "failure"
    status_context: str = "mergeguard/policy"

    @field_validator("webhook_url")
    @classmethod
    def _check_webhook_url(cls, v: str) -> str:
        if v:
            from mergeguard.output.notifications import _validate_webhook_url

            _validate_webhook_url(v)
        return v


class PolicyRule(BaseModel):
    """A named policy rule with conditions and actions."""

    name: str
    description: str = ""
    conditions: list[PolicyCondition]
    actions: list[PolicyAction]
    enabled: bool = True


class PolicyResult(BaseModel):
    """Evaluation result for a single policy rule."""

    policy_name: str
    matched: bool
    conditions_evaluated: list[dict[str, Any]] = Field(default_factory=list)
    actions_to_execute: list[PolicyAction] = Field(default_factory=list)


class PolicyEvaluationResult(BaseModel):
    """Aggregate result of evaluating all policy rules."""

    results: list[PolicyResult] = Field(default_factory=list)
    actions: list[PolicyAction] = Field(default_factory=list)
    evaluated_at: datetime

    @property
    def has_block(self) -> bool:
        return any(a.action == PolicyActionType.BLOCK_MERGE for a in self.actions)

    @property
    def matched_policies(self) -> list[str]:
        return [r.policy_name for r in self.results if r.matched]


class PolicyConfig(BaseModel):
    """Configuration for the policy engine."""

    enabled: bool = False
    policies: list[PolicyRule] = Field(default_factory=list)


class SecretPattern(BaseModel):
    """A single secret detection pattern."""

    name: str  # e.g. "AWS Access Key"
    pattern: str  # Regex pattern, e.g. r"AKIA[0-9A-Z]{16}"
    severity: ConflictSeverity = ConflictSeverity.CRITICAL


class SecretsConfig(BaseModel):
    """Configuration for secret scanning in PR diffs."""

    enabled: bool = False  # Opt-in only — V1 focuses on conflict detection
    use_builtin_patterns: bool = True
    patterns: list[SecretPattern] = Field(default_factory=list)
    allowlist: list[str] = Field(default_factory=list)
    ignored_paths: list[str] = Field(
        default_factory=lambda: [
            "tests/**",
            "**/test_*",
            "**/tests/**",
            "**/*_test.*",
            "**/*.test.*",
            "**/fixtures/**",
            "**/testdata/**",
        ]
    )


class MetricsConfig(BaseModel):
    """Configuration for DORA metrics tracking."""

    enabled: bool = False
    retention_days: int = 90
    time_windows: list[int] = Field(default_factory=lambda: [7, 30, 90])


class MetricsSnapshot(BaseModel):
    """A single snapshot of a PR's conflict state at analysis time."""

    pr_number: int
    repo: str
    analyzed_at: datetime
    risk_score: float
    conflict_count: int
    severity_max: str  # "critical" | "warning" | "info" | "none"
    resolved_at: datetime | None = None
    resolution_type: str | None = None  # "merged" | "closed"


class DORAMetrics(BaseModel):
    """DORA-style metrics for a single time window."""

    window_days: int
    period_start: datetime
    period_end: datetime
    merge_count: int = 0
    merges_per_day: float = 0.0
    total_prs_analyzed: int = 0
    prs_with_conflicts: int = 0
    conflict_rate: float = 0.0
    resolution_times_hours: list[float] = Field(default_factory=list)
    mean_resolution_time_hours: float = 0.0
    median_resolution_time_hours: float = 0.0
    p90_resolution_time_hours: float = 0.0
    mttrc_hours: float = 0.0
    unresolved_count: int = 0


class DORAReport(BaseModel):
    """Aggregate DORA metrics report across multiple time windows."""

    repo: str
    generated_at: datetime
    windows: list[DORAMetrics] = Field(default_factory=list)


class MergeGuardConfig(BaseModel):
    """Configuration loaded from .mergeguard.yml."""

    model_config = ConfigDict(extra="forbid")

    inline_annotations: bool = True  # Post line-level review comments alongside summary
    risk_threshold: int = 50  # Only comment if risk > threshold
    check_regressions: bool = True
    max_open_prs: int = 200  # Safety cap (not the primary filter)
    max_pr_age_days: int = 30  # Only scan PRs updated within this many days
    decisions_log_depth: int = 50  # How many merged PRs to track
    llm_enabled: bool = False
    llm_model: str = "claude-sonnet-4-20250514"
    llm_provider: str = "auto"  # "auto" | "openai" | "anthropic"
    fix_suggestions: bool = False  # LLM-enhanced suggestions (templates always active)
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
    risk_weights: dict[str, float] | None = None  # Custom risk scoring weights (must sum to ~1.0)
    max_transitive_per_pair: int = 5  # Max transitive conflicts per PR pair
    max_transitive_depth: int = 1  # BFS depth for transitive dependency traversal
    github_url: str | None = None  # GitHub Enterprise Server URL (e.g., https://github.example.com)
    max_file_size: int = 500_000  # Max file size in bytes (skip larger files)
    max_diff_size: int = 100_000  # Max diff size in bytes (truncate larger diffs)
    churn_max_lines: int = 500  # Lines changed for max churn score (1.0)
    max_cache_entries: int = 500  # Max entries in analysis cache
    api_timeout: int = 30  # HTTP timeout in seconds
    max_workers: int = 8  # Max concurrent workers for parallel operations
    server: ServerConfig = Field(default_factory=ServerConfig)
    codeowners: CodeownersConfig = Field(default_factory=CodeownersConfig)
    merge_queue: MergeQueueConfig = Field(default_factory=MergeQueueConfig)
    stacked_prs: StackedPRConfig = Field(default_factory=StackedPRConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
