"""Format ConflictReport as a GitHub PR comment."""

from __future__ import annotations

from mergeguard.models import (
    Conflict,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
)

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
}


def format_report(report: ConflictReport, repo_full_name: str) -> str:
    """Format a ConflictReport as a GitHub Markdown comment.

    Design principles:
    - Scannable: severity emoji + bold type makes it easy to triage
    - Actionable: every conflict includes a specific recommendation
    - Non-blocking: info-level conflicts are collapsed
    - Linkable: PR references are clickable GitHub links
    """
    lines: list[str] = []

    # Header with risk score
    risk_emoji = _risk_emoji(report.risk_score)
    lines.append(f"## {risk_emoji} MergeGuard: Cross-PR Analysis")
    lines.append("")

    if report.risk_score > 0:
        lines.append(
            f"**Risk Score: {report.risk_score:.0f}/100** | "
            f"{len(report.conflicts)} conflict(s) detected"
        )
        lines.append("")

    # Critical and warning conflicts — shown prominently
    important = [
        c
        for c in report.conflicts
        if c.severity in (ConflictSeverity.CRITICAL, ConflictSeverity.WARNING)
    ]
    if important:
        for conflict in important:
            lines.append(_format_conflict(conflict, repo_full_name))
            lines.append("")

    # Info-level conflicts — collapsed
    info_conflicts = [c for c in report.conflicts if c.severity == ConflictSeverity.INFO]
    if info_conflicts:
        lines.append("<details>")
        lines.append(
            f"<summary>\u2139\ufe0f {len(info_conflicts)} low-severity overlap(s)</summary>"
        )
        lines.append("")
        for conflict in info_conflicts:
            lines.append(_format_conflict(conflict, repo_full_name))
            lines.append("")
        lines.append("</details>")
        lines.append("")

    # Clean PRs
    if report.no_conflict_prs:
        pr_links = ", ".join(f"#{n}" for n in sorted(report.no_conflict_prs))
        lines.append(f"\u2705 **No conflicts with:** {pr_links}")
        lines.append("")

    # No conflicts at all
    if not report.conflicts:
        lines.append(
            "\u2705 **No cross-PR conflicts detected.** This PR is clear to review."
        )
        lines.append("")

    # Footer
    lines.append("---")
    lines.append(
        f"<sub>Analysis completed in {report.analysis_duration_ms}ms | "
        f"[MergeGuard](https://github.com/mergeguard/mergeguard) v0.1</sub>"
    )

    return "\n".join(lines)


def _format_conflict(conflict: Conflict, repo_full_name: str) -> str:
    emoji = SEVERITY_EMOJI[conflict.severity]
    type_label = TYPE_LABELS[conflict.conflict_type]
    pr_link = (
        f"[#{conflict.target_pr}]"
        f"(https://github.com/{repo_full_name}/pull/{conflict.target_pr})"
    )

    lines = [
        f"### {emoji} {type_label} with {pr_link}",
        f"**File:** `{conflict.file_path}`",
    ]

    if conflict.symbol_name:
        lines.append(f"**Symbol:** `{conflict.symbol_name}`")

    lines.append(f"\n{conflict.description}")
    lines.append(f"\n\U0001f4a1 **Recommendation:** {conflict.recommendation}")

    return "\n".join(lines)


def _risk_emoji(score: float) -> str:
    if score >= 70:
        return "\U0001f534"
    if score >= 40:
        return "\U0001f7e1"
    return "\U0001f7e2"
