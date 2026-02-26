"""Rich-based CLI display for MergeGuard reports.

Provides beautiful terminal output with color-coded severity,
tables for risk scores, and detailed conflict views.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from mergeguard.models import ConflictReport, ConflictSeverity

console = Console()


def display_report(report: ConflictReport) -> None:
    """Display a single PR analysis report in the terminal."""
    if not report.conflicts:
        console.print(
            f"\n[green]\u2705 PR #{report.pr.number} has no cross-PR conflicts![/green]\n"
        )
        return

    console.print(f"\n[bold]MergeGuard Report \u2014 PR #{report.pr.number}[/bold]")
    console.print(f"Risk Score: {report.risk_score:.0f}/100\n")

    for conflict in report.conflicts:
        sev_color = {"critical": "red", "warning": "yellow", "info": "dim"}
        color = sev_color.get(conflict.severity.value, "white")
        console.print(
            f"  [{color}]\u25cf {conflict.severity.value.upper()}[/{color}] "
            f"{conflict.conflict_type.value} with #{conflict.target_pr}"
        )
        console.print(f"    File: {conflict.file_path}")
        if conflict.symbol_name:
            console.print(f"    Symbol: {conflict.symbol_name}")
        console.print(f"    {conflict.description}")
        console.print(f"    \U0001f4a1 {conflict.recommendation}\n")


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
            "red"
            if report.risk_score >= 70
            else "yellow"
            if report.risk_score >= 40
            else "green"
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


def display_collision_map(
    pr_titles: list[tuple[int, str]], overlap_matrix: dict[int, dict[int, int]]
) -> None:
    """Display the collision map showing file overlaps between PRs."""
    table = Table(title="PR Collision Map", show_lines=True)
    table.add_column("PR", style="bold cyan")

    for num, _ in pr_titles:
        table.add_column(f"#{num}", justify="center")

    for num_a, title_a in pr_titles:
        row = [f"#{num_a} {title_a[:30]}"]
        for num_b, _ in pr_titles:
            if num_a == num_b:
                row.append("\u2014")
            else:
                count = overlap_matrix.get(num_a, {}).get(num_b, 0)
                if count > 0:
                    row.append(f"[red]{count} file(s)[/red]")
                else:
                    row.append("[green]\u2713[/green]")
        table.add_row(*row)

    console.print(table)
