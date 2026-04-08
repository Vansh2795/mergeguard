"""Format ConflictReport as a GitHub PR comment."""

from __future__ import annotations

from itertools import groupby
from operator import attrgetter

from mergeguard.models import (
    Conflict,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
)
from mergeguard.output._sanitize import escape_backticks, sanitize_markdown

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


def _pr_link(repo: str, number: int, platform: str = "github") -> str:
    """Generate a clickable PR/MR link for the given platform."""
    if platform == "gitlab":
        return f"[!{number}](https://gitlab.com/{repo}/-/merge_requests/{number})"
    return f"[#{number}](https://github.com/{repo}/pull/{number})"


def format_report(
    report: ConflictReport,
    repo_full_name: str,
    *,
    platform: str = "github",
    inline_count: int = 0,
) -> str:
    """Format a ConflictReport as a Markdown comment.

    Design principles:
    - Scannable: severity emoji + bold type makes it easy to triage
    - Actionable: every conflict includes a specific recommendation
    - Non-blocking: info-level conflicts are collapsed
    - Linkable: PR references are clickable links
    """
    lines: list[str] = []

    # Header with risk score
    risk_emoji = _risk_emoji(report.risk_score)
    logo_url = "https://raw.githubusercontent.com/Vansh2795/mergeguard/main/assets/logo.svg"
    lines.append(
        f'## <img src="{logo_url}" height="24" alt=""> {risk_emoji} MergeGuard: Cross-PR Analysis'
    )
    lines.append("")

    if report.risk_score > 0:
        lines.append(
            f"**Risk Score: {report.risk_score:.0f}/100** | "
            f"{len(report.conflicts)} conflict(s) detected"
        )
        if inline_count > 0:
            lines.append(
                f"> {inline_count} conflict(s) annotated inline on the diff. "
                f"See review comments for details."
            )
        lines.append("")

    # Stack context banner
    if report.stack_group and report.stack_pr_numbers:
        stack_parts = []
        for pr_num in report.stack_pr_numbers:
            if pr_num == report.pr.number:
                stack_parts.append(f"**#{pr_num}**")
            else:
                stack_parts.append(f"#{pr_num}")
        stack_str = " \u2192 ".join(stack_parts)
        pos = report.stack_position or 0
        total = len(report.stack_pr_numbers)
        lines.append(f"> \U0001f4e6 **Part of stack:** {stack_str} (position {pos}/{total})")
        lines.append("")

    # Critical and warning conflicts — grouped by target PR (excluding intra-stack)
    important = [
        c
        for c in report.conflicts
        if c.severity in (ConflictSeverity.CRITICAL, ConflictSeverity.WARNING)
        and not c.is_intra_stack
    ]
    if important:
        grouped = groupby(
            sorted(important, key=attrgetter("target_pr")),
            key=attrgetter("target_pr"),
        )
        for target_pr, conflicts_iter in grouped:
            conflicts_list = list(conflicts_iter)
            link = _pr_link(repo_full_name, target_pr, platform)
            if len(conflicts_list) > 4:
                # Collapse large groups
                crit = sum(1 for c in conflicts_list if c.severity == ConflictSeverity.CRITICAL)
                warn = sum(1 for c in conflicts_list if c.severity == ConflictSeverity.WARNING)
                parts = []
                if crit:
                    parts.append(f"{crit} critical")
                if warn:
                    parts.append(f"{warn} warning")
                summary = ", ".join(parts)
                lines.append(f"### Conflicts with {link}")
                lines.append("")
                lines.append("<details>")
                lines.append(f"<summary>{summary} — expand for details</summary>")
                lines.append("")
                for conflict in conflicts_list:
                    lines.append(_format_conflict_compact(conflict, repo_full_name))
                    lines.append("")
                lines.append("</details>")
                lines.append("")
            else:
                lines.append(f"### Conflicts with {link}")
                lines.append("")
                for conflict in conflicts_list:
                    lines.append(_format_conflict_compact(conflict, repo_full_name))
                    lines.append("")

    # Intra-stack conflicts — collapsed section
    intra_stack_conflicts = [c for c in report.conflicts if c.is_intra_stack]
    if intra_stack_conflicts:
        lines.append("<details>")
        lines.append(
            f"<summary>\U0001f4e6 {len(intra_stack_conflicts)} intra-stack "
            f"conflict(s) (expected)</summary>"
        )
        lines.append("")
        for conflict in intra_stack_conflicts:
            orig = (
                f"Originally {conflict.original_severity.value.upper()} \u2014 demoted (same stack)"
                if conflict.original_severity
                else "Same stack"
            )
            lines.append(_format_conflict_compact(conflict, repo_full_name) + f"\n*{orig}*")
            lines.append("")
        lines.append("</details>")
        lines.append("")

    # Info-level conflicts — collapsed, also grouped (excluding intra-stack)
    info_conflicts = [
        c for c in report.conflicts if c.severity == ConflictSeverity.INFO and not c.is_intra_stack
    ]
    if info_conflicts:
        lines.append("<details>")
        lines.append(
            f"<summary>\u2139\ufe0f {len(info_conflicts)} low-severity overlap(s)</summary>"
        )
        lines.append("")
        info_grouped = groupby(
            sorted(info_conflicts, key=attrgetter("target_pr")),
            key=attrgetter("target_pr"),
        )
        for target_pr, conflicts_iter in info_grouped:
            conflicts_list = list(conflicts_iter)
            link = _pr_link(repo_full_name, target_pr, platform)
            lines.append(f"#### {link}")
            lines.append("")
            for conflict in conflicts_list:
                lines.append(_format_conflict_compact(conflict, repo_full_name))
                lines.append("")
        lines.append("</details>")
        lines.append("")

    # Clean PRs
    if report.no_conflict_prs:
        pr_links = ", ".join(f"#{n}" for n in sorted(report.no_conflict_prs))
        lines.append(f"\u2705 **No conflicts with:** {pr_links}")
        lines.append("")

    # Skipped files
    if report.pr.skipped_files:
        lines.append("<details>")
        lines.append(
            f"<summary>\u26a0\ufe0f {len(report.pr.skipped_files)} file(s) skipped "
            f"(no patch data)</summary>"
        )
        lines.append("")
        for path in report.pr.skipped_files:
            lines.append(f"- `{path}`")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # No conflicts at all
    if not report.conflicts:
        lines.append("\u2705 **No cross-PR conflicts detected.** This PR is clear to review.")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append(
        f"<sub>Analysis completed in {report.analysis_duration_ms}ms | "
        f"[MergeGuard](https://github.com/mergeguard/mergeguard) v0.1</sub>"
    )

    return "\n".join(lines)


def _format_conflict(conflict: Conflict, repo_full_name: str, platform: str = "github") -> str:
    emoji = SEVERITY_EMOJI[conflict.severity]
    type_label = TYPE_LABELS[conflict.conflict_type]
    link = _pr_link(repo_full_name, conflict.target_pr, platform)

    lines = [
        f"### {emoji} {type_label} with {link}",
        f"**File:** `{conflict.file_path}`",
    ]

    if conflict.symbol_name:
        lines.append(f"**Symbol:** `{conflict.symbol_name}`")

    if conflict.owners:
        lines.append(f"**Owners:** {' '.join(conflict.owners)}")

    lines.append(f"\n{conflict.description}")
    lines.append(f"\n\U0001f4a1 **Recommendation:** {conflict.recommendation}")

    if conflict.fix_suggestion is not None:
        lines.append(f"\n\U0001f527 **Suggested Fix:** {conflict.fix_suggestion}")

    return "\n".join(lines)


def _format_conflict_compact(conflict: Conflict, repo_full_name: str) -> str:
    """Format a conflict without a per-conflict PR link (used in grouped output)."""
    emoji = SEVERITY_EMOJI[conflict.severity]
    type_label = TYPE_LABELS[conflict.conflict_type]

    lines = [
        f"{emoji} **{type_label}** — `{escape_backticks(conflict.file_path)}`",
    ]

    if conflict.symbol_name:
        lines.append(f"**Symbol:** `{escape_backticks(conflict.symbol_name)}`")

    if conflict.owners:
        lines.append(f"**Owners:** {' '.join(conflict.owners)}")

    lines.append(sanitize_markdown(conflict.description))
    lines.append(f"\U0001f4a1 {sanitize_markdown(conflict.recommendation)}")

    if conflict.fix_suggestion is not None:
        lines.append(f"\U0001f527 **Suggested Fix:** {sanitize_markdown(conflict.fix_suggestion)}")

    return "\n".join(lines)


def _risk_emoji(score: float) -> str:
    if score >= 70:
        return "\U0001f534"
    if score >= 40:
        return "\U0001f7e1"
    return "\U0001f7e2"
