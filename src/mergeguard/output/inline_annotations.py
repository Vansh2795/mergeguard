"""Format Conflicts as inline review comments for PR annotations."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mergeguard.integrations.protocol import ReviewComment
    from mergeguard.models import ConflictReport

from mergeguard.models import Conflict, ConflictSeverity, ConflictType

SEVERITY_EMOJI = {
    ConflictSeverity.CRITICAL: "\U0001f534",
    ConflictSeverity.WARNING: "\u26a0\ufe0f",
    ConflictSeverity.INFO: "\u2139\ufe0f",
}

TYPE_LABELS = {
    ConflictType.HARD: "Hard Conflict",
    ConflictType.INTERFACE: "Interface Conflict",
    ConflictType.BEHAVIORAL: "Behavioral Conflict",
    ConflictType.DUPLICATION: "Duplication Detected",
    ConflictType.TRANSITIVE: "Transitive Conflict",
    ConflictType.REGRESSION: "Regression Detected",
    ConflictType.GUARDRAIL: "Guardrail Violation",
    ConflictType.SECRET: "Secret Detected",
}


def format_review_comments(
    report: ConflictReport,
    repo: str,
    *,
    platform: str = "github",
    max_comments: int = 50,
) -> list[ReviewComment]:
    """Convert conflicts with line info into ReviewComment objects.

    Conflicts without source_lines are skipped (they'll still appear
    in the summary comment). Capped at max_comments to avoid API limits.
    """
    from mergeguard.integrations.protocol import ReviewComment

    comments: list[ReviewComment] = []

    # Sort by severity (critical first) then file path for deterministic output
    annotatable = [c for c in report.conflicts if c.source_lines is not None]
    annotatable.sort(key=lambda c: (c.severity != ConflictSeverity.CRITICAL, c.file_path))

    for conflict in annotatable[:max_comments]:
        if conflict.source_lines is None:
            continue
        body = _format_annotation_body(conflict, repo, platform)
        comments.append(
            ReviewComment(
                path=conflict.file_path,
                line=conflict.source_lines[0],
                body=body,
            )
        )

    return comments


def format_review_summary(report: ConflictReport, inline_count: int) -> str:
    """Format the review body (top-level summary for the review)."""
    total = len(report.conflicts)
    lines = [
        f"**MergeGuard** found **{total}** conflict(s) (risk score: {report.risk_score:.0f}/100).",
    ]
    skipped = total - inline_count
    if skipped > 0:
        lines.append(
            f"\n{inline_count} conflict(s) annotated inline. "
            f"{skipped} conflict(s) without line info \u2014 see summary comment."
        )
    return "\n".join(lines)


def _format_annotation_body(conflict: Conflict, repo: str, platform: str) -> str:
    """Format a single inline annotation body."""
    emoji = SEVERITY_EMOJI[conflict.severity]
    type_label = TYPE_LABELS[conflict.conflict_type]

    prefix = ""
    if conflict.is_intra_stack:
        prefix = "\U0001f4e6 **Intra-stack** (expected) \u2014 "

    lines = [f"{prefix}{emoji} **{type_label}** \u2014 conflicts with PR #{conflict.target_pr}"]

    if conflict.symbol_name:
        lines.append(f"**Symbol:** `{conflict.symbol_name}`")

    from mergeguard.output._sanitize import sanitize_markdown

    lines.append(f"\n{sanitize_markdown(conflict.description)}")
    lines.append(f"\n> {sanitize_markdown(conflict.recommendation)}")

    if conflict.fix_suggestion:
        lines.append(f"\n**Suggested fix:** {sanitize_markdown(conflict.fix_suggestion)}")

    return "\n".join(lines)
