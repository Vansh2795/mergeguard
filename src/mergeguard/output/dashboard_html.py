"""Static HTML dashboard generator for MergeGuard.

Generates a single self-contained HTML file with Chart.js visualizations:
- PR collision matrix
- Risk score distribution
- Conflict type breakdown
- Historical trends (when data available)
"""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mergeguard.models import ConflictReport


def format_dashboard_html(reports: list[ConflictReport], repo: str) -> str:
    """Generate a self-contained HTML dashboard with Chart.js visualizations."""
    # Prepare data for charts
    pr_data = []
    type_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    collision_matrix: dict[int, dict[int, int]] = {}

    for report in reports:
        pr_data.append({
            "number": report.pr.number,
            "title": report.pr.title[:40],
            "risk_score": round(report.risk_score, 1),
            "conflicts": len(report.conflicts),
            "author": report.pr.author,
            "ai": report.pr.ai_attribution.value.startswith("ai"),
        })

        for c in report.conflicts:
            type_counts[c.conflict_type.value] = type_counts.get(c.conflict_type.value, 0) + 1
            severity_counts[c.severity.value] = severity_counts.get(c.severity.value, 0) + 1
            collision_matrix.setdefault(c.source_pr, {})
            collision_matrix[c.source_pr][c.target_pr] = (
                collision_matrix[c.source_pr].get(c.target_pr, 0) + 1
            )

    pr_data_json = json.dumps(pr_data)
    type_counts_json = json.dumps(type_counts)
    severity_counts_json = json.dumps(severity_counts)

    # Build table rows
    table_rows = _build_dashboard_table(reports)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MergeGuard Dashboard - {html.escape(repo)}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #0f172a; color: #e2e8f0; }}
.container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
.header {{ text-align: center; padding: 30px 0; }}
.header h1 {{ font-size: 28px; color: #f1f5f9; }}
.header .subtitle {{ color: #94a3b8; margin-top: 4px; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
.card {{ background: #1e293b; border-radius: 12px; padding: 24px;
         box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
.card h3 {{ color: #f1f5f9; margin-bottom: 16px; font-size: 16px; }}
.card canvas {{ max-height: 300px; }}
.full-width {{ grid-column: 1 / -1; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ background: #334155; padding: 12px 16px; text-align: left; font-size: 12px;
     text-transform: uppercase; color: #94a3b8; cursor: pointer; }}
th:hover {{ background: #475569; }}
td {{ padding: 10px 16px; border-top: 1px solid #334155; }}
.risk-high {{ color: #ef4444; font-weight: bold; }}
.risk-med {{ color: #f59e0b; font-weight: bold; }}
.risk-low {{ color: #22c55e; font-weight: bold; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px;
          font-size: 11px; font-weight: 600; }}
.badge-critical {{ background: rgba(239,68,68,0.2); color: #ef4444; }}
.badge-warning {{ background: rgba(245,158,11,0.2); color: #f59e0b; }}
.badge-info {{ background: rgba(59,130,246,0.2); color: #3b82f6; }}
.footer {{ text-align: center; padding: 24px; color: #64748b; font-size: 12px; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
                 margin-bottom: 20px; }}
.summary-card {{ background: #1e293b; border-radius: 12px; padding: 20px; text-align: center; }}
.summary-value {{ font-size: 36px; font-weight: bold; }}
.summary-label {{ font-size: 12px; color: #94a3b8; text-transform: uppercase; margin-top: 4px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>MergeGuard Dashboard</h1>
    <div class="subtitle">{html.escape(repo)} &mdash; {len(reports)} open PRs</div>
  </div>

  <div class="summary-grid">
    <div class="summary-card">
      <div class="summary-value" style="color: #3b82f6">{len(reports)}</div>
      <div class="summary-label">Open PRs</div>
    </div>
    <div class="summary-card">
      <div class="summary-value" style="color: #ef4444">{severity_counts.get("critical", 0)}</div>
      <div class="summary-label">Critical</div>
    </div>
    <div class="summary-card">
      <div class="summary-value" style="color: #f59e0b">{severity_counts.get("warning", 0)}</div>
      <div class="summary-label">Warnings</div>
    </div>
    <div class="summary-card">
      <div class="summary-value" style="color: #22c55e">\
{sum(1 for r in reports if not r.conflicts)}</div>
      <div class="summary-label">Clean PRs</div>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h3>Risk Score Distribution</h3>
      <canvas id="riskChart"></canvas>
    </div>
    <div class="card">
      <h3>Conflict Types</h3>
      <canvas id="typeChart"></canvas>
    </div>
    <div class="card">
      <h3>Severity Breakdown</h3>
      <canvas id="severityChart"></canvas>
    </div>
    <div class="card">
      <h3>Risk by PR</h3>
      <canvas id="prRiskChart"></canvas>
    </div>
  </div>

  <div class="card full-width" style="grid-column: 1 / -1; margin-bottom: 20px;">
    <h3>PR Risk Table</h3>
    <table id="prTable">
      <thead>
        <tr>
          <th onclick="sortDashTable(0)">PR</th>
          <th onclick="sortDashTable(1)">Title</th>
          <th onclick="sortDashTable(2)">Author</th>
          <th onclick="sortDashTable(3)">Risk</th>
          <th onclick="sortDashTable(4)">Conflicts</th>
          <th>Breakdown</th>
        </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
  </div>

  <div class="footer">
    Generated by MergeGuard
  </div>
</div>

<script>
const prData = {pr_data_json};
const typeCounts = {type_counts_json};
const severityCounts = {severity_counts_json};

// Risk distribution histogram
const riskBuckets = [0,0,0,0,0]; // 0-20, 20-40, 40-60, 60-80, 80-100
prData.forEach(pr => {{
  const idx = Math.min(4, Math.floor(pr.risk_score / 20));
  riskBuckets[idx]++;
}});

new Chart(document.getElementById('riskChart'), {{
  type: 'bar',
  data: {{
    labels: ['0-20', '20-40', '40-60', '60-80', '80-100'],
    datasets: [{{ label: 'PRs', data: riskBuckets,
      backgroundColor: ['#22c55e','#84cc16','#f59e0b','#f97316','#ef4444'] }}]
  }},
  options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{
    y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }},
    x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }}
  }} }}
}});

// Conflict type pie
new Chart(document.getElementById('typeChart'), {{
  type: 'doughnut',
  data: {{
    labels: Object.keys(typeCounts),
    datasets: [{{ data: Object.values(typeCounts),
      backgroundColor: ['#ef4444','#f59e0b','#3b82f6','#8b5cf6','#06b6d4','#22c55e','#f97316'] }}]
  }},
  options: {{ plugins: {{ legend: {{ labels: {{ color: '#94a3b8' }} }} }} }}
}});

// Severity pie
new Chart(document.getElementById('severityChart'), {{
  type: 'doughnut',
  data: {{
    labels: Object.keys(severityCounts).map(s => s.charAt(0).toUpperCase() + s.slice(1)),
    datasets: [{{ data: Object.values(severityCounts),
      backgroundColor: ['#ef4444','#f59e0b','#3b82f6'] }}]
  }},
  options: {{ plugins: {{ legend: {{ labels: {{ color: '#94a3b8' }} }} }} }}
}});

// Risk by PR bar
new Chart(document.getElementById('prRiskChart'), {{
  type: 'bar',
  data: {{
    labels: prData.map(p => '#' + p.number),
    datasets: [{{ label: 'Risk Score', data: prData.map(p => p.risk_score),
      backgroundColor: prData.map(p => p.risk_score >= 70 ? '#ef4444' :
        p.risk_score >= 40 ? '#f59e0b' : '#22c55e') }}]
  }},
  options: {{ indexAxis: 'y', plugins: {{ legend: {{ display: false }} }}, scales: {{
    x: {{ max: 100, ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }},
    y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }}
  }} }}
}});

function sortDashTable(col) {{
  const table = document.getElementById('prTable');
  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows);
  const asc = table.dataset.sortCol == col && table.dataset.sortDir !== 'asc';
  rows.sort((a, b) => {{
    let av = a.cells[col].textContent.trim();
    let bv = b.cells[col].textContent.trim();
    const an = parseFloat(av), bn = parseFloat(bv);
    if (!isNaN(an) && !isNaN(bn)) return asc ? an - bn : bn - an;
    return asc ? av.localeCompare(bv) : bv.localeCompare(av);
  }});
  rows.forEach(r => tbody.appendChild(r));
  table.dataset.sortCol = col;
  table.dataset.sortDir = asc ? 'asc' : 'desc';
}}
</script>
</body>
</html>"""


def _build_dashboard_table(reports: list[ConflictReport]) -> str:
    """Build HTML table rows for the dashboard."""
    rows = []
    for report in sorted(reports, key=lambda r: r.risk_score, reverse=True):
        risk_class = (
            "risk-high" if report.risk_score >= 70
            else "risk-med" if report.risk_score >= 40
            else "risk-low"
        )
        severity_badges = []
        counts = report.conflict_count_by_severity
        for sev in ["critical", "warning", "info"]:
            count = counts.get(sev, 0)
            if count > 0:
                severity_badges.append(
                    f'<span class="badge badge-{sev}">{count} {sev}</span>'
                )

        ai_badge = ' <span class="badge badge-warning">AI</span>' if (
            report.pr.ai_attribution.value.startswith("ai")
        ) else ""

        rows.append(
            f"<tr>"
            f"<td>#{report.pr.number}</td>"
            f"<td>{html.escape(report.pr.title[:40])}{ai_badge}</td>"
            f"<td>{html.escape(report.pr.author)}</td>"
            f'<td class="{risk_class}">{report.risk_score:.0f}</td>'
            f"<td>{len(report.conflicts)}</td>"
            f"<td>{' '.join(severity_badges) or '<span style=\"color:#64748b\">clean</span>'}</td>"
            f"</tr>"
        )
    return "\n".join(rows)
