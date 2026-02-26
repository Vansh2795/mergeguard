"""MergeGuard CLI — Cross-PR intelligence from your terminal."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
@click.version_option()
def main():
    """MergeGuard: Cross-PR intelligence for the agentic coding era."""
    pass


@main.command()
@click.option("--repo", "-r", help="GitHub repo (owner/repo). Auto-detected from git remote.")
@click.option("--pr", "-p", type=int, help="PR number to analyze. Defaults to current branch.")
@click.option("--token", "-t", envvar="GITHUB_TOKEN", help="GitHub token.")
@click.option("--config", "-c", default=".mergeguard.yml", help="Config file path.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["terminal", "json", "markdown"]),
    default="terminal",
)
@click.option("--llm/--no-llm", default=False, help="Enable LLM-powered semantic analysis.")
@click.option(
    "--post-comment/--no-post-comment",
    default=False,
    help="Post results as a GitHub PR comment.",
)
def analyze(repo, pr, token, config, output_format, llm, post_comment):
    """Analyze a PR for cross-PR conflicts."""
    from mergeguard.config import load_config
    from mergeguard.core.engine import MergeGuardEngine

    cfg = load_config(config)
    if llm:
        cfg.llm_enabled = True

    with console.status("[bold blue]Analyzing cross-PR conflicts...", spinner="dots"):
        engine = MergeGuardEngine(
            token=token,
            repo_full_name=repo,
            config=cfg,
        )
        report = engine.analyze_pr(pr)

    if output_format == "terminal":
        _display_terminal(report)
    elif output_format == "json":
        click.echo(report.model_dump_json(indent=2))
    elif output_format == "markdown":
        from mergeguard.output.github_comment import format_report

        click.echo(format_report(report, repo))

    if post_comment and token:
        from mergeguard.integrations.github_client import GitHubClient
        from mergeguard.output.github_comment import format_report

        client = GitHubClient(token, repo)
        client.post_pr_comment(pr, format_report(report, repo))
        console.print("[green]\u2713 Comment posted to PR[/green]")


@main.command()
@click.option("--repo", "-r", help="GitHub repo (owner/repo).")
@click.option("--token", "-t", envvar="GITHUB_TOKEN")
def map(repo, token):
    """Show the collision map of all open PRs."""
    from mergeguard.core.conflict import compute_file_overlaps
    from mergeguard.integrations.github_client import GitHubClient

    client = GitHubClient(token, repo)
    prs = client.get_open_prs()

    # Enrich with file data
    for pr_info in prs:
        pr_info.changed_files = client.get_pr_files(pr_info.number)

    table = Table(title=f"PR Collision Map \u2014 {repo}", show_lines=True)
    table.add_column("PR", style="bold cyan")
    for pr_info in prs:
        table.add_column(f"#{pr_info.number}", justify="center")

    for i, pr_a in enumerate(prs):
        row = [f"#{pr_a.number} {pr_a.title[:30]}"]
        for j, pr_b in enumerate(prs):
            if i == j:
                row.append("\u2014")
            else:
                overlaps = compute_file_overlaps(pr_a, [pr_b])
                if pr_b.number in overlaps:
                    count = len(overlaps[pr_b.number])
                    row.append(f"[red]{count} file(s)[/red]")
                else:
                    row.append("[green]\u2713[/green]")
        table.add_row(*row)

    console.print(table)


@main.command()
@click.option("--repo", "-r", help="GitHub repo (owner/repo).")
@click.option("--token", "-t", envvar="GITHUB_TOKEN")
def dashboard(repo, token):
    """Show risk scores for all open PRs."""
    from mergeguard.config import load_config
    from mergeguard.core.engine import MergeGuardEngine

    cfg = load_config(".mergeguard.yml")
    engine = MergeGuardEngine(token=token, repo_full_name=repo, config=cfg)

    with console.status("[bold blue]Analyzing all open PRs...", spinner="dots"):
        reports = engine.analyze_all_open_prs()

    table = Table(title=f"PR Risk Dashboard \u2014 {repo}")
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


def _display_terminal(report):
    """Rich terminal display for a single PR analysis."""
    from mergeguard.models import ConflictSeverity

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
