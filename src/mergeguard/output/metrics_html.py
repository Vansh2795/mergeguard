"""Self-contained HTML report for DORA metrics with Chart.js visualizations."""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mergeguard.models import DORAReport


def format_metrics_html(report: DORAReport) -> str:
    """Generate a self-contained HTML report with Chart.js charts for DORA metrics."""
    repo = html.escape(report.repo)
    generated = report.generated_at.strftime("%Y-%m-%d %H:%M UTC")

    # Prepare chart data
    window_labels = json.dumps([f"{w.window_days}d" for w in report.windows])
    merge_counts = json.dumps([w.merge_count for w in report.windows])
    merges_per_day = json.dumps([w.merges_per_day for w in report.windows])
    conflict_rates = json.dumps([round(w.conflict_rate * 100, 1) for w in report.windows])
    mean_times = json.dumps([w.mean_resolution_time_hours for w in report.windows])
    median_times = json.dumps([w.median_resolution_time_hours for w in report.windows])
    p90_times = json.dumps([w.p90_resolution_time_hours for w in report.windows])

    # Summary cards (use first window if available)
    total_merges = report.windows[0].merge_count if report.windows else 0
    conflict_rate_pct = round(report.windows[0].conflict_rate * 100, 1) if report.windows else 0
    mttrc = report.windows[0].mttrc_hours if report.windows else 0
    unresolved = report.windows[0].unresolved_count if report.windows else 0

    # Pre-compute card colors
    crp = conflict_rate_pct
    cr_color = "#22c55e" if crp < 20 else "#f59e0b" if crp < 50 else "#ef4444"
    mttrc_color = "#22c55e" if mttrc < 24 else "#f59e0b" if mttrc < 72 else "#ef4444"
    ur_color = "#22c55e" if unresolved == 0 else "#f59e0b" if unresolved < 5 else "#ef4444"

    # Build table rows
    table_rows = _build_metrics_table(report)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DORA Metrics - {repo}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #0f172a; color: #e2e8f0; }}
.container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
.header {{ text-align: center; padding: 30px 0; }}
.header h1 {{ font-size: 28px; color: #f1f5f9; }}
.header .subtitle {{ color: #94a3b8; margin-top: 4px; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
                 margin-bottom: 20px; }}
.summary-card {{ background: #1e293b; border-radius: 12px; padding: 20px; text-align: center; }}
.summary-value {{ font-size: 36px; font-weight: bold; }}
.summary-label {{ font-size: 12px; color: #94a3b8; text-transform: uppercase; margin-top: 4px; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
.card {{ background: #1e293b; border-radius: 12px; padding: 24px;
         box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
.card h3 {{ color: #f1f5f9; margin-bottom: 16px; font-size: 16px; }}
.card canvas {{ max-height: 300px; }}
.full-width {{ grid-column: 1 / -1; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ background: #334155; padding: 12px 16px; text-align: left; font-size: 12px;
     text-transform: uppercase; color: #94a3b8; }}
td {{ padding: 10px 16px; border-top: 1px solid #334155; }}
.good {{ color: #22c55e; }}
.warn {{ color: #f59e0b; }}
.bad {{ color: #ef4444; }}
.footer {{ text-align: center; padding: 24px; color: #64748b; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>DORA Metrics</h1>
    <div class="subtitle">{repo} &mdash; Generated {generated}</div>
  </div>

  <div class="summary-grid">
    <div class="summary-card">
      <div class="summary-value" style="color: #3b82f6">{total_merges}</div>
      <div class="summary-label">Total Merges</div>
    </div>
    <div class="summary-card">
      <div class="summary-value" style="color: {cr_color}">{conflict_rate_pct}%</div>
      <div class="summary-label">Conflict Rate</div>
    </div>
    <div class="summary-card">
      <div class="summary-value" style="color: {mttrc_color}">{mttrc:.1f}h</div>
      <div class="summary-label">MTTRC</div>
    </div>
    <div class="summary-card">
      <div class="summary-value" style="color: {ur_color}">{unresolved}</div>
      <div class="summary-label">Unresolved</div>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h3>Merge Frequency</h3>
      <canvas id="mergeChart"></canvas>
    </div>
    <div class="card">
      <h3>Resolution Time Distribution</h3>
      <canvas id="resolutionChart"></canvas>
    </div>
  </div>

  <div class="card full-width" style="margin-bottom: 20px;">
    <h3>Metrics Breakdown</h3>
    <table>
      <thead>
        <tr>
          <th>Window</th>
          <th>Merges</th>
          <th>Merges/Day</th>
          <th>Conflict Rate</th>
          <th>Mean Res.</th>
          <th>Median Res.</th>
          <th>P90 Res.</th>
          <th>MTTRC</th>
          <th>Unresolved</th>
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
const labels = {window_labels};
const mergeCounts = {merge_counts};
const mergesPerDay = {merges_per_day};
const conflictRates = {conflict_rates};
const meanTimes = {mean_times};
const medianTimes = {median_times};
const p90Times = {p90_times};

new Chart(document.getElementById('mergeChart'), {{
  type: 'bar',
  data: {{
    labels: labels,
    datasets: [
      {{ label: 'Total Merges', data: mergeCounts,
         backgroundColor: '#3b82f6', yAxisID: 'y' }},
      {{ label: 'Merges/Day', data: mergesPerDay,
         type: 'line', borderColor: '#22c55e', backgroundColor: 'transparent',
         yAxisID: 'y1', tension: 0.3 }}
    ]
  }},
  options: {{
    plugins: {{ legend: {{ labels: {{ color: '#94a3b8' }} }} }},
    scales: {{
      y: {{ position: 'left', ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }},
      y1: {{ position: 'right', ticks: {{ color: '#94a3b8' }}, grid: {{ display: false }} }},
      x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }}
    }}
  }}
}});

new Chart(document.getElementById('resolutionChart'), {{
  type: 'bar',
  data: {{
    labels: labels,
    datasets: [
      {{ label: 'Mean', data: meanTimes, backgroundColor: '#3b82f6' }},
      {{ label: 'Median', data: medianTimes, backgroundColor: '#22c55e' }},
      {{ label: 'P90', data: p90Times, backgroundColor: '#f59e0b' }}
    ]
  }},
  options: {{
    plugins: {{ legend: {{ labels: {{ color: '#94a3b8' }} }} }},
    scales: {{
      y: {{ ticks: {{ color: '#94a3b8', callback: v => v + 'h' }}, grid: {{ color: '#334155' }} }},
      x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }}
    }}
  }}
}});
</script>
</body>
</html>"""


def _build_metrics_table(report: DORAReport) -> str:
    """Build HTML table rows for the metrics breakdown."""
    rows = []
    for w in report.windows:
        rate_pct = round(w.conflict_rate * 100, 1)
        rate_cls = "good" if rate_pct < 20 else "warn" if rate_pct < 50 else "bad"
        mean_h = w.mean_resolution_time_hours
        mean_cls = "good" if mean_h < 24 else "warn" if mean_h < 72 else "bad"
        uc = w.unresolved_count
        unresolved_cls = "good" if uc == 0 else "warn" if uc < 5 else "bad"

        rows.append(
            f"<tr>"
            f"<td>{w.window_days}d</td>"
            f"<td>{w.merge_count}</td>"
            f"<td>{w.merges_per_day:.2f}</td>"
            f'<td class="{rate_cls}">{rate_pct}%</td>'
            f'<td class="{mean_cls}">{w.mean_resolution_time_hours:.1f}h</td>'
            f"<td>{w.median_resolution_time_hours:.1f}h</td>"
            f"<td>{w.p90_resolution_time_hours:.1f}h</td>"
            f'<td class="{mean_cls}">{w.mttrc_hours:.1f}h</td>'
            f'<td class="{unresolved_cls}">{w.unresolved_count}</td>'
            f"</tr>"
        )
    return "\n".join(rows)
