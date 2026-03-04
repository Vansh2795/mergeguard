"""Machine-readable JSON output for MergeGuard reports.

Produces JSON reports suitable for CI/CD integration,
custom dashboards, and programmatic consumption.
"""

from __future__ import annotations

import json
import os
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

    Uses GITHUB_OUTPUT env var when available (standard Actions mechanism),
    falls back to /tmp files with restrictive permissions.
    """
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a") as f:
            f.write(f"risk_score={report.risk_score:.0f}\n")
            f.write(f"conflict_count={len(report.conflicts)}\n")
    else:
        for name, value in [("score", f"{report.risk_score:.0f}"),
                            ("conflicts", str(len(report.conflicts)))]:
            fd = os.open(f"/tmp/mergeguard-{name}.txt",
                         os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(value)


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
