"""Self-contained HTML report generator for MergeGuard."""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mergeguard.models import Conflict, ConflictReport

_SEVERITY_COLORS = {
    "critical": "#e74c3c",
    "warning": "#f39c12",
    "info": "#3498db",
}

_SEVERITY_LABELS = {
    "critical": "Critical",
    "warning": "Warning",
    "info": "Info",
}


def format_html_report(report: ConflictReport, repo: str) -> str:
    """Generate a self-contained HTML file with embedded CSS/JS."""
    conflicts_json = json.dumps(
        [
            {
                "type": c.conflict_type.value,
                "severity": c.severity.value,
                "source_pr": c.source_pr,
                "target_pr": c.target_pr,
                "file_path": c.file_path,
                "symbol_name": c.symbol_name or "",
                "description": c.description,
                "recommendation": c.recommendation,
                "fix_suggestion": c.fix_suggestion or "",
                "cross_file": getattr(c, "cross_file", False),
                "source_diff": c.source_diff_preview or "",
                "target_diff": c.target_diff_preview or "",
            }
            for c in report.conflicts
        ]
    )

    factors_json = json.dumps(report.risk_factors)

    severity_counts = report.conflict_count_by_severity
    critical_count = severity_counts.get("critical", 0)
    warning_count = severity_counts.get("warning", 0)
    info_count = severity_counts.get("info", 0)

    conflict_rows = _build_conflict_rows(report.conflicts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MergeGuard Report - PR #{report.pr.number}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #f5f6fa; color: #2c3e50; line-height: 1.6; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
.header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
           color: white; padding: 30px; border-radius: 12px; margin-bottom: 24px; }}
.header h1 {{ font-size: 24px; margin-bottom: 8px; }}
.header .subtitle {{ opacity: 0.9; }}
.risk-gauge {{ display: flex; align-items: center; gap: 20px; margin-top: 16px; }}
.risk-score {{ font-size: 48px; font-weight: bold; }}
.risk-label {{ font-size: 14px; opacity: 0.8; }}
.stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          gap: 16px; margin-bottom: 24px; }}
.stat-card {{ background: white; padding: 20px; border-radius: 8px;
              box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }}
.stat-value {{ font-size: 28px; font-weight: bold; }}
.stat-label {{ font-size: 12px; color: #7f8c8d; text-transform: uppercase; }}
.conflicts-table {{ background: white; border-radius: 8px; overflow: hidden;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
.conflicts-table table {{ width: 100%; border-collapse: collapse; }}
.conflicts-table th {{ background: #f8f9fa; padding: 12px 16px; text-align: left;
                       font-size: 12px; text-transform: uppercase; color: #7f8c8d;
                       cursor: pointer; user-select: none; }}
.conflicts-table th:hover {{ background: #e9ecef; }}
.conflicts-table td {{ padding: 12px 16px; border-top: 1px solid #eee; }}
.severity-badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px;
                   font-size: 12px; font-weight: 600; color: white; }}
.severity-critical {{ background: {_SEVERITY_COLORS["critical"]}; }}
.severity-warning {{ background: {_SEVERITY_COLORS["warning"]}; }}
.severity-info {{ background: {_SEVERITY_COLORS["info"]}; }}
.diff-preview {{ background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 4px;
                 font-family: 'Fira Code', monospace; font-size: 12px; overflow-x: auto;
                 margin-top: 8px; white-space: pre; }}
.diff-add {{ color: #4ec9b0; }}
.diff-del {{ color: #f44747; }}
.details {{ cursor: pointer; color: #3498db; font-size: 13px; }}
.hidden {{ display: none; }}
.factors {{ background: white; padding: 20px; border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 24px; }}
.factor-bar {{ display: flex; align-items: center; gap: 12px; margin: 8px 0; }}
.factor-name {{ width: 160px; font-size: 13px; }}
.factor-track {{ flex: 1; height: 20px; background: #ecf0f1;
  border-radius: 10px; overflow: hidden; }}
.factor-fill {{ height: 100%; border-radius: 10px; transition: width 0.5s; }}
.factor-value {{ width: 50px; text-align: right; font-size: 13px; font-weight: 600; }}
.footer {{ text-align: center; padding: 20px; color: #95a5a6; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>MergeGuard Report</h1>
    <div class="subtitle">\
PR #{report.pr.number}: {html.escape(report.pr.title)} &mdash; {html.escape(repo)}</div>
    <div class="risk-gauge">
      <div>
        <div class="risk-score">{report.risk_score:.0f}</div>
        <div class="risk-label">Risk Score</div>
      </div>
    </div>
  </div>

  <div class="stats">
    <div class="stat-card">
      <div class="stat-value" style="color: {_SEVERITY_COLORS["critical"]}">{critical_count}</div>
      <div class="stat-label">Critical</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color: {_SEVERITY_COLORS["warning"]}">{warning_count}</div>
      <div class="stat-label">Warning</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color: {_SEVERITY_COLORS["info"]}">{info_count}</div>
      <div class="stat-label">Info</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{len(report.no_conflict_prs)}</div>
      <div class="stat-label">Clean PRs</div>
    </div>
  </div>

  <div class="factors">
    <h3 style="margin-bottom: 12px;">Risk Factors</h3>
    {_build_factor_bars(report.risk_factors)}
  </div>

  <div class="conflicts-table">
    <table id="conflictsTable">
      <thead>
        <tr>
          <th onclick="sortTable(0)">Severity</th>
          <th onclick="sortTable(1)">Type</th>
          <th onclick="sortTable(2)">Target PR</th>
          <th onclick="sortTable(3)">File</th>
          <th>Details</th>
        </tr>
      </thead>
      <tbody>
        {conflict_rows}
      </tbody>
    </table>
  </div>

  <div class="footer">
    <p>Generated by MergeGuard in {report.analysis_duration_ms}ms</p>
  </div>
</div>

<script>
const conflicts = {conflicts_json};
const factors = {factors_json};

function sortTable(col) {{
  const table = document.getElementById('conflictsTable');
  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows);
  const asc = table.dataset.sortCol == col && table.dataset.sortDir !== 'asc';
  rows.sort((a, b) => {{
    const av = a.cells[col].textContent.trim();
    const bv = b.cells[col].textContent.trim();
    return asc ? av.localeCompare(bv) : bv.localeCompare(av);
  }});
  rows.forEach(r => tbody.appendChild(r));
  table.dataset.sortCol = col;
  table.dataset.sortDir = asc ? 'asc' : 'desc';
}}

function toggleDetails(id) {{
  const el = document.getElementById(id);
  el.classList.toggle('hidden');
}}
</script>
</body>
</html>"""


def _build_factor_bars(factors: dict[str, float]) -> str:
    """Build HTML for risk factor progress bars."""
    colors = {
        "conflict_severity": "#e74c3c",
        "blast_radius": "#e67e22",
        "pattern_deviation": "#f39c12",
        "churn_risk": "#3498db",
        "ai_attribution": "#9b59b6",
    }
    labels = {
        "conflict_severity": "Conflict Severity",
        "blast_radius": "Blast Radius",
        "pattern_deviation": "Pattern Deviation",
        "churn_risk": "Churn Risk",
        "ai_attribution": "AI Attribution",
    }
    bars = []
    for key, value in factors.items():
        color = colors.get(key, "#95a5a6")
        label = labels.get(key, key.replace("_", " ").title())
        width = min(100, max(0, value))
        bars.append(
            f'<div class="factor-bar">'
            f'<div class="factor-name">{html.escape(label)}</div>'
            f'<div class="factor-track">'
            f'<div class="factor-fill" style="width: {width}%; background: {color};"></div>'
            f"</div>"
            f'<div class="factor-value">{value:.0f}</div>'
            f"</div>"
        )
    return "\n".join(bars)


def _build_conflict_rows(conflicts: list[Conflict]) -> str:
    """Build HTML table rows for conflicts."""
    rows = []
    for i, c in enumerate(conflicts):
        sev_class = f"severity-{c.severity.value}"
        sev_label = _SEVERITY_LABELS.get(c.severity.value, c.severity.value)
        detail_id = f"detail-{i}"

        diff_html = ""
        if c.source_diff_preview:
            src_diff = _colorize_diff(html.escape(c.source_diff_preview))
            diff_html += f'<div class="diff-preview">{src_diff}</div>'
        if c.target_diff_preview:
            tgt_diff = _colorize_diff(html.escape(c.target_diff_preview))
            diff_html += f'<div class="diff-preview">{tgt_diff}</div>'

        symbol = f" <code>{html.escape(c.symbol_name)}</code>" if c.symbol_name else ""
        cross = " (cross-file)" if getattr(c, "cross_file", False) else ""

        rows.append(
            f"<tr>"
            f'<td><span class="severity-badge {sev_class}">{sev_label}</span></td>'
            f"<td>{c.conflict_type.value}{cross}</td>"
            f"<td>#{c.target_pr}</td>"
            f"<td><code>{html.escape(c.file_path)}</code>{symbol}</td>"
            f'<td><span class="details" onclick="toggleDetails(\'{detail_id}\')">Show</span>'
            f'<div id="{detail_id}" class="hidden" style="margin-top:8px;">'
            f"<p>{html.escape(c.description)}</p>"
            f"<p><strong>Recommendation:</strong> {html.escape(c.recommendation)}</p>"
            f"{diff_html}"
            f"</div></td>"
            f"</tr>"
        )
    return "\n".join(rows)


def _colorize_diff(escaped_diff: str) -> str:
    """Add color spans to diff lines (already HTML-escaped)."""
    lines = []
    for line in escaped_diff.split("\n"):
        if line.startswith("+"):
            lines.append(f'<span class="diff-add">{line}</span>')
        elif line.startswith("-"):
            lines.append(f'<span class="diff-del">{line}</span>')
        else:
            lines.append(line)
    return "\n".join(lines)
