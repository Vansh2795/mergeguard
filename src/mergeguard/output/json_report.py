"""Machine-readable JSON output for MergeGuard reports.

Produces JSON reports suitable for CI/CD integration,
custom dashboards, and programmatic consumption.
"""

from __future__ import annotations

import json
from pathlib import Path

from mergeguard.models import ConflictReport


def format_json_report(report: ConflictReport, pretty: bool = True) -> str:
    """Format a ConflictReport as JSON.

    Args:
        report: The conflict report to format.
        pretty: Whether to pretty-print the JSON.

    Returns:
        JSON string representation of the report.
    """
    indent = 2 if pretty else None
    return report.model_dump_json(indent=indent)


def write_json_report(report: ConflictReport, output_path: str | Path) -> None:
    """Write a ConflictReport to a JSON file.

    Args:
        report: The conflict report to write.
        output_path: File path for the JSON output.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(format_json_report(report))


def write_github_action_outputs(report: ConflictReport) -> None:
    """Write report data as GitHub Actions outputs.

    Creates files that GitHub Actions reads for step outputs:
    - /tmp/mergeguard-score.txt
    - /tmp/mergeguard-conflicts.txt
    """
    Path("/tmp/mergeguard-score.txt").write_text(f"{report.risk_score:.0f}")
    Path("/tmp/mergeguard-conflicts.txt").write_text(str(len(report.conflicts)))


def format_summary(report: ConflictReport) -> dict:
    """Create a summary dict suitable for CI status descriptions.

    Returns:
        Dict with keys: risk_score, conflict_count, has_critical, status
    """
    status = "pass"
    if report.has_critical:
        status = "fail"
    elif report.conflicts:
        status = "warn"

    return {
        "risk_score": report.risk_score,
        "conflict_count": len(report.conflicts),
        "has_critical": report.has_critical,
        "status": status,
        "severity_breakdown": report.conflict_count_by_severity,
    }
