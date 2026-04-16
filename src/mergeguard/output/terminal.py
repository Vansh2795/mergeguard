"""Rich-based CLI display for MergeGuard reports.

Provides beautiful terminal output with color-coded severity,
tables for risk scores, and detailed conflict views.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

if TYPE_CHECKING:
    from mergeguard.models import Conflict, ConflictReport

console = Console()


def display_report(report: ConflictReport) -> None:
    """Display a single PR analysis report in the terminal."""
    if not report.conflicts:
        console.print(
            f"\n[green]\u2705 PR #{report.pr.number} has no cross-PR conflicts![/green]\n"
        )
        return

    console.print(f"\n[bold]MergeGuard Report \u2014 PR #{report.pr.number}[/bold]")
    console.print(f"Risk Score: {report.risk_score:.0f}/100")

    # Stack context
    if report.stack_group and report.stack_pr_numbers:
        stack_str = " \u2192 ".join(f"#{n}" for n in report.stack_pr_numbers)
        console.print(f"\U0001f4e6 Stack: {stack_str}")

    console.print()

    from itertools import groupby
    from operator import attrgetter

    # Split into cross-stack and intra-stack conflicts
    cross_stack = [c for c in report.conflicts if not c.is_intra_stack]
    intra_stack = [c for c in report.conflicts if c.is_intra_stack]

    sorted_conflicts = sorted(cross_stack, key=attrgetter("target_pr"))
    for target_pr, conflicts_iter in groupby(sorted_conflicts, key=attrgetter("target_pr")):
        conflicts_list = list(conflicts_iter)
        if len(conflicts_list) > 4:
            console.print(
                f"  [bold cyan]Conflicts with #{target_pr}[/bold cyan] "
                f"({len(conflicts_list)} conflicts)"
            )
        else:
            console.print(f"  [bold cyan]Conflicts with #{target_pr}[/bold cyan]")
        for conflict in conflicts_list:
            sev_color = {"critical": "red", "warning": "yellow", "info": "dim"}
            color = sev_color.get(conflict.severity.value, "white")
            console.print(
                f"    [{color}]\u25cf {conflict.severity.value.upper()}[/{color}] "
                f"{conflict.conflict_type.value}"
            )
            console.print(f"      File: {conflict.file_path}")
            if conflict.symbol_name:
                console.print(f"      Symbol: {conflict.symbol_name}")
            console.print(f"      {conflict.description}")
            console.print(f"      \U0001f4a1 {conflict.recommendation}")
            if conflict.fix_suggestion is not None:
                console.print(f"      \U0001f527 {conflict.fix_suggestion}")
            # Diff previews (collapsed by default in rich via Panel)
            if conflict.source_diff_preview or conflict.target_diff_preview:
                _render_diff_previews(conflict)
            console.print()

    # Intra-stack conflicts (dimmed)
    if intra_stack:
        console.print(
            f"  [dim]\U0001f4e6 {len(intra_stack)} intra-stack conflict(s) (expected):[/dim]"
        )
        for conflict in intra_stack:
            orig = (
                f" (was {conflict.original_severity.value.upper()})"
                if conflict.original_severity
                else ""
            )
            console.print(
                f"    [dim]\u25cf {conflict.conflict_type.value} "
                f"with #{conflict.target_pr} — {conflict.file_path}{orig}[/dim]"
            )
        console.print()

    if report.pr.skipped_files:
        console.print("[dim]Files skipped (no patch data):[/dim]")
        for path in report.pr.skipped_files:
            console.print(f"  [dim]- {path}[/dim]")


def display_dashboard(reports: list[ConflictReport], repo_name: str) -> None:
    """Display the risk dashboard for all open PRs."""
    table = Table(title=f"PR Risk Dashboard \u2014 {repo_name}")
    table.add_column("PR", style="bold")
    table.add_column("Title")
    table.add_column("Risk", justify="right")
    table.add_column("Conflicts", justify="right")
    table.add_column("AI?", justify="center")

    for report in sorted(reports, key=lambda r: r.risk_score, reverse=True):
        risk_style = (
            "red" if report.risk_score >= 70 else "yellow" if report.risk_score >= 40 else "green"
        )
        ai = "\U0001f916" if report.pr.ai_attribution.value.startswith("ai") else ""
        table.add_row(
            f"#{report.pr.number}",
            report.pr.title[:40],
            f"[{risk_style}]{report.risk_score:.0f}[/{risk_style}]",
            str(len(report.conflicts)),
            ai,
        )

    console.print(table)


def _render_diff_previews(conflict: Conflict) -> None:
    """Render source and target diff previews with syntax highlighting."""
    if conflict.source_diff_preview:
        syntax = Syntax(
            conflict.source_diff_preview,
            "diff",
            theme="monokai",
            line_numbers=False,
        )
        console.print(
            Panel(syntax, title=f"PR #{conflict.source_pr} diff", border_style="dim", width=80)
        )
    if conflict.target_diff_preview:
        syntax = Syntax(
            conflict.target_diff_preview,
            "diff",
            theme="monokai",
            line_numbers=False,
        )
        console.print(
            Panel(syntax, title=f"PR #{conflict.target_pr} diff", border_style="dim", width=80)
        )
