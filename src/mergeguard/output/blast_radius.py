"""Blast radius visualization — graph-based conflict topology.

Builds a PR-level conflict graph with transitive blast radius computation,
and renders it as an interactive D3.js force-directed graph (HTML),
Rich terminal output, or raw JSON.
"""

from __future__ import annotations

import html as _html
from collections import defaultdict, deque
from datetime import datetime
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from mergeguard.analysis.dependency import DependencyGraph

from mergeguard.models import (
    BlastRadiusData,
    BlastRadiusEdge,
    BlastRadiusNode,
    ConflictReport,
)

_SEVERITY_ORDER = {"critical": 2, "warning": 1, "info": 0}


def _max_severity(a: str, b: str) -> str:
    """Return the higher of two severity strings."""
    return a if _SEVERITY_ORDER.get(a, -1) >= _SEVERITY_ORDER.get(b, -1) else b


def build_blast_radius_data(
    reports: list[ConflictReport],
    repo: str,
    file_graph: DependencyGraph | None = None,
) -> BlastRadiusData:
    """Build the complete blast radius graph from conflict reports."""
    # 1. Build PR collision adjacency from reports
    # Key: frozenset({source_pr, target_pr}) → list of conflicts
    edge_map: dict[frozenset[int], list[Any]] = defaultdict(list)
    pr_conflicts: dict[int, list[Any]] = defaultdict(list)

    for report in reports:
        for conflict in report.conflicts:
            pair = frozenset({conflict.source_pr, conflict.target_pr})
            edge_map[pair].append(conflict)
            pr_conflicts[conflict.source_pr].append(conflict)

    # Build adjacency list for BFS
    adjacency: dict[int, set[int]] = defaultdict(set)
    for pair in edge_map:
        nums = list(pair)
        if len(nums) == 2:
            adjacency[nums[0]].add(nums[1])
            adjacency[nums[1]].add(nums[0])

    # 2. Build nodes from reports
    nodes: list[BlastRadiusNode] = []
    for report in reports:
        pr_num = report.pr.number
        direct_neighbors = adjacency.get(pr_num, set())
        direct_blast = len(direct_neighbors)

        # BFS for transitive blast radius
        visited: set[int] = set()
        queue: deque[int] = deque([pr_num])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        visited.discard(pr_num)
        transitive_blast = len(visited)

        # Max severity across all conflicts for this PR
        sev_max = "info"
        for conflict in pr_conflicts.get(pr_num, []):
            sev_max = _max_severity(sev_max, conflict.severity.value)

        # If no conflicts at all, show "none"
        if not pr_conflicts.get(pr_num):
            sev_max = "none"

        nodes.append(
            BlastRadiusNode(
                pr_number=pr_num,
                title=report.pr.title,
                author=report.pr.author,
                risk_score=report.risk_score,
                conflict_count=len(pr_conflicts.get(pr_num, [])),
                direct_blast=direct_blast,
                transitive_blast=transitive_blast,
                severity_max=sev_max,
                stack_group=report.stack_group,
                ai_authored=report.pr.ai_attribution.value.startswith("ai"),
                files_changed=[f.path for f in report.pr.changed_files],
            )
        )

    # 3. Build edges
    edges: list[BlastRadiusEdge] = []
    for pair, conflicts in edge_map.items():
        nums = sorted(pair)
        if len(nums) != 2:
            continue
        sev_max = "info"
        types: set[str] = set()
        files: set[str] = set()
        is_intra = False
        for c in conflicts:
            sev_max = _max_severity(sev_max, c.severity.value)
            types.add(c.conflict_type.value)
            files.add(c.file_path)
            if c.is_intra_stack:
                is_intra = True

        edges.append(
            BlastRadiusEdge(
                source_pr=nums[0],
                target_pr=nums[1],
                conflict_count=len(conflicts),
                severity_max=sev_max,
                conflict_types=sorted(types),
                is_intra_stack=is_intra,
                files=sorted(files),
            )
        )

    # 4. File-level edges from dependency graph
    file_edges: list[dict[str, Any]] = []
    if file_graph is not None:
        # Collect all changed files across reports
        all_changed: set[str] = set()
        for report in reports:
            for f in report.pr.changed_files:
                all_changed.add(f.path)

        for edge in file_graph.edges:
            if edge.source_file in all_changed or edge.target_file in all_changed:
                file_edges.append(
                    {
                        "source": edge.source_file,
                        "target": edge.target_file,
                        "symbols": edge.imported_names,
                    }
                )

    # 5. Stack groups
    stack_groups: list[dict[str, Any]] = []
    seen_groups: set[str] = set()
    for report in reports:
        if report.stack_group and report.stack_group not in seen_groups:
            seen_groups.add(report.stack_group)
            stack_groups.append(
                {
                    "group_id": report.stack_group,
                    "pr_numbers": report.stack_pr_numbers,
                }
            )

    return BlastRadiusData(
        nodes=nodes,
        edges=edges,
        file_edges=file_edges,
        stack_groups=stack_groups,
        repo=repo,
        generated_at=datetime.now(tz=None),
    )


def format_blast_radius_json(data: BlastRadiusData) -> str:
    """Serialize blast radius data as JSON."""
    return data.model_dump_json(indent=2)


def format_blast_radius_terminal(data: BlastRadiusData) -> None:
    """Render blast radius data as Rich terminal output."""
    console = Console(stderr=True)

    # Summary table
    table = Table(title=f"Blast Radius — {data.repo}")
    table.add_column("PR", style="bold cyan")
    table.add_column("Title")
    table.add_column("Risk", justify="right")
    table.add_column("Direct", justify="right")
    table.add_column("Transitive", justify="right")
    table.add_column("Stack")

    for node in sorted(data.nodes, key=lambda n: n.transitive_blast, reverse=True):
        risk_style = (
            "red" if node.risk_score >= 70 else "yellow" if node.risk_score >= 40 else "green"
        )
        stack_label = node.stack_group or "—"
        table.add_row(
            f"#{node.pr_number}",
            node.title[:30],
            f"[{risk_style}]{node.risk_score:.0f}[/{risk_style}]",
            str(node.direct_blast),
            str(node.transitive_blast),
            stack_label,
        )

    console.print(table)

    # Conflict graph (ASCII adjacency)
    if data.edges:
        console.print("\n[bold]Conflict Graph[/bold]")
        for edge in data.edges:
            sev_color = {"critical": "red", "warning": "yellow", "info": "dim"}.get(
                edge.severity_max, "white"
            )
            types_str = ", ".join(f"{edge.severity_max.upper()} {t}" for t in edge.conflict_types)
            suffix = " [intra-stack]" if edge.is_intra_stack else ""
            console.print(
                f"  [{sev_color}]#{edge.source_pr} ←→ #{edge.target_pr}[/{sev_color}] "
                f"({edge.conflict_count} conflict{'s' if edge.conflict_count != 1 else ''}: "
                f"{types_str}){suffix}"
            )


def format_blast_radius_html(data: BlastRadiusData) -> str:
    """Generate a self-contained HTML page with D3.js force-directed graph."""
    data_json = data.model_dump_json()
    repo_escaped = _html.escape(data.repo)

    total_prs = len(data.nodes)
    total_conflicts = sum(e.conflict_count for e in data.edges)
    avg_risk = sum(n.risk_score for n in data.nodes) / total_prs if total_prs else 0

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Blast Radius — {repo_escaped}</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #0f172a; color: #e2e8f0; overflow: hidden; }}
.header {{ padding: 16px 24px; background: #1e293b; border-bottom: 1px solid #334155;
           display: flex; align-items: center; justify-content: space-between; z-index: 10; }}
.header h1 {{ font-size: 20px; color: #f1f5f9; }}
.header .subtitle {{ color: #94a3b8; font-size: 13px; }}
.header .stats {{ display: flex; gap: 20px; }}
.stat {{ text-align: center; }}
.stat-value {{ font-size: 22px; font-weight: bold; }}
.stat-label {{ font-size: 10px; color: #94a3b8; text-transform: uppercase; }}
.main {{ display: flex; height: calc(100vh - 60px); }}
.graph-container {{ flex: 1; position: relative; }}
svg {{ width: 100%; height: 100%; }}
.sidebar {{ width: 320px; background: #1e293b; border-left: 1px solid #334155;
            overflow-y: auto; padding: 16px; display: none; }}
.sidebar.visible {{ display: block; }}
.sidebar h3 {{ color: #f1f5f9; margin-bottom: 12px; font-size: 16px; }}
.sidebar .close {{ float: right; cursor: pointer; color: #94a3b8; font-size: 18px; }}
.sidebar .close:hover {{ color: #f1f5f9; }}
.detail-row {{ padding: 8px 0; border-bottom: 1px solid #334155; font-size: 13px; }}
.detail-label {{ color: #94a3b8; font-size: 11px; text-transform: uppercase; }}
.detail-value {{ color: #e2e8f0; margin-top: 2px; }}
.file-list {{ list-style: none; padding: 0; max-height: 200px; overflow-y: auto; }}
.file-list li {{ padding: 2px 0; font-size: 12px; color: #94a3b8; font-family: monospace; }}
.controls {{ position: absolute; top: 12px; left: 12px; display: flex; gap: 8px;
             flex-wrap: wrap; z-index: 5; }}
.controls button, .controls select, .controls input {{
    background: #1e293b; border: 1px solid #475569; color: #e2e8f0;
    padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; }}
.controls button:hover {{ background: #334155; }}
.controls input {{ width: 120px; }}
.legend {{ position: absolute; bottom: 12px; left: 12px; background: rgba(30,41,59,0.9);
           padding: 12px; border-radius: 8px; font-size: 11px; z-index: 5; }}
.legend-item {{ display: flex; align-items: center; gap: 6px; margin: 4px 0; }}
.legend-dot {{ width: 12px; height: 12px; border-radius: 50%; }}
.legend-line {{ width: 20px; height: 0; border-top: 2px solid; }}
.legend-line.dashed {{ border-top-style: dashed; }}
.tooltip {{ position: absolute; background: #1e293b; border: 1px solid #475569;
            padding: 10px 14px; border-radius: 8px; font-size: 12px; pointer-events: none;
            z-index: 20; display: none; max-width: 300px; }}
.conflict-item {{ padding: 6px 0; border-bottom: 1px solid #334155; font-size: 12px; }}
.badge {{ display: inline-block; padding: 1px 6px; border-radius: 8px;
          font-size: 10px; font-weight: 600; }}
.badge-critical {{ background: rgba(239,68,68,0.2); color: #ef4444; }}
.badge-warning {{ background: rgba(245,158,11,0.2); color: #f59e0b; }}
.badge-info {{ background: rgba(59,130,246,0.2); color: #3b82f6; }}
.badge-none {{ background: rgba(100,116,139,0.2); color: #94a3b8; }}
.hull {{ fill-opacity: 0.08; stroke-opacity: 0.3; stroke-width: 1.5; }}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>Blast Radius</h1>
    <div class="subtitle">{repo_escaped}</div>
  </div>
  <div class="stats">
    <div class="stat">
      <div class="stat-value" style="color:#3b82f6">{total_prs}</div>
      <div class="stat-label">PRs</div>
    </div>
    <div class="stat">
      <div class="stat-value" style="color:#ef4444">{total_conflicts}</div>
      <div class="stat-label">Conflicts</div>
    </div>
    <div class="stat">
      <div class="stat-value" style="color:#f59e0b">{avg_risk:.0f}</div>
      <div class="stat-label">Avg Risk</div>
    </div>
  </div>
</div>

<div class="main">
  <div class="graph-container">
    <div class="controls">
      <button id="resetBtn" title="Reset layout">Reset</button>
      <select id="severityFilter">
        <option value="all">All severities</option>
        <option value="critical">Critical only</option>
        <option value="warning">Warning+</option>
      </select>
      <label style="display:flex;align-items:center;gap:4px;font-size:12px;color:#94a3b8">
        <input type="checkbox" id="toggleIntraStack" checked> Intra-stack
      </label>
      <input type="text" id="searchPR" placeholder="Search PR #...">
    </div>
    <svg id="graph"></svg>
    <div class="legend">
      <div style="font-weight:600;margin-bottom:6px">
        Legend</div>
      <div class="legend-item">
        <div class="legend-dot" style="background:#ef4444">
        </div> Critical</div>
      <div class="legend-item">
        <div class="legend-dot" style="background:#f59e0b">
        </div> Warning</div>
      <div class="legend-item">
        <div class="legend-dot" style="background:#3b82f6">
        </div> Info</div>
      <div class="legend-item">
        <div class="legend-dot" style="background:#64748b">
        </div> No conflicts</div>
      <div style="margin-top:6px;color:#94a3b8">
        Size = risk score</div>
      <div class="legend-item">
        <div class="legend-line dashed"
          style="border-color:#94a3b8"></div>
        Intra-stack</div>
    </div>
    <div class="tooltip" id="tooltip"></div>
  </div>
  <div class="sidebar" id="sidebar">
    <span class="close" id="closeSidebar">&times;</span>
    <div id="sidebarContent"></div>
  </div>
</div>

<script>
const DATA = {data_json};

const severityColor = {{
  critical: '#ef4444', warning: '#f59e0b', info: '#3b82f6', none: '#64748b'
}};

const svg = d3.select('#graph');
const width = svg.node().parentElement.clientWidth;
const height = svg.node().parentElement.clientHeight;

const g = svg.append('g');

// Zoom
const zoom = d3.zoom().scaleExtent([0.2, 4]).on('zoom', e => g.attr('transform', e.transform));
svg.call(zoom);

// Stack hulls
const stackGroupMap = {{}};
DATA.stack_groups.forEach(sg => {{
  sg.pr_numbers.forEach(n => {{ stackGroupMap[n] = sg.group_id; }});
}});
const hullColors = ['#8b5cf6', '#06b6d4', '#f97316', '#22c55e', '#ec4899'];

// Force simulation
const nodeData = DATA.nodes.map(n => ({{ ...n, id: n.pr_number }}));
const linkData = DATA.edges.map(e => ({{ ...e, source: e.source_pr, target: e.target_pr }}));
const nodeMap = Object.fromEntries(nodeData.map(n => [n.id, n]));

const simulation = d3.forceSimulation(nodeData)
  .force('link', d3.forceLink(linkData).id(d => d.id).distance(140))
  .force('charge', d3.forceManyBody().strength(-400))
  .force('center', d3.forceCenter(width / 2, height / 2))
  .force('collision', d3.forceCollide().radius(d => radiusScale(d.risk_score) + 8));

const radiusScale = d3.scaleLinear().domain([0, 100]).range([15, 45]).clamp(true);
const linkWidthScale = d3.scaleLinear().domain([1, 10]).range([1, 4]).clamp(true);

// Draw hulls
const hullG = g.append('g').attr('class', 'hulls');

// Draw links
const linkG = g.append('g').attr('class', 'links');
let linkEl = linkG.selectAll('line').data(linkData).enter().append('line')
  .attr('stroke', d => severityColor[d.severity_max] || '#64748b')
  .attr('stroke-width', d => linkWidthScale(d.conflict_count))
  .attr('stroke-dasharray', d => d.is_intra_stack ? '6,4' : null)
  .attr('stroke-opacity', 0.6);

// Draw nodes
const nodeG = g.append('g').attr('class', 'nodes');
let nodeEl = nodeG.selectAll('g').data(nodeData)
  .enter().append('g').call(d3.drag()
    .on('start', (e, d) => {{
      if (!e.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x; d.fy = d.y;
    }})
    .on('drag', (e, d) => {{
      d.fx = e.x; d.fy = e.y;
    }})
    .on('end', (e, d) => {{
      if (!e.active) simulation.alphaTarget(0);
      d.fx = null; d.fy = null;
    }}));

nodeEl.append('circle')
  .attr('r', d => radiusScale(d.risk_score))
  .attr('fill', d => severityColor[d.severity_max] || '#64748b')
  .attr('fill-opacity', 0.85)
  .attr('stroke', '#f1f5f9')
  .attr('stroke-width', 1.5);

nodeEl.append('text')
  .text(d => '#' + d.pr_number)
  .attr('text-anchor', 'middle')
  .attr('dy', '0.35em')
  .attr('fill', '#f1f5f9')
  .attr('font-size', '11px')
  .attr('font-weight', '600')
  .attr('pointer-events', 'none');

// Tooltip
const tooltip = d3.select('#tooltip');

nodeEl.on('mouseover', (e, d) => {{
  const t = `<strong>#${{d.pr_number}}</strong> `
    + `${{escHtml(d.title)}}<br>`
    + `Author: ${{escHtml(d.author)}}<br>`
    + `Risk: ${{d.risk_score.toFixed(0)}} &middot; `
    + `Blast: ${{d.direct_blast}} direct, `
    + `${{d.transitive_blast}} transitive`;
  tooltip.style('display', 'block').html(t);
}}).on('mousemove', e => {{
  tooltip.style('left', (e.pageX+14)+'px')
    .style('top', (e.pageY-10)+'px');
}}).on('mouseout', () => tooltip.style('display', 'none'));

// Click node → sidebar
nodeEl.on('click', (e, d) => {{
  if (e.shiftKey && DATA.file_edges.length) {{
    showFileEdges(d);
    return;
  }}
  showSidebar(d);
}});

// Edge tooltips
linkEl.on('mouseover', (e, d) => {{
  tooltip.style('display', 'block')
    .html(`#${{d.source_pr || d.source.id}} &harr; #${{d.target_pr || d.target.id}}<br>
           ${{d.conflict_count}} conflict(s): ${{d.conflict_types.join(', ')}}<br>
           Files: ${{d.files.slice(0, 3).join(', ')}}${{d.files.length > 3 ? '...' : ''}}`);
}}).on('mousemove', e => {{
  tooltip.style('left', (e.pageX + 14) + 'px').style('top', (e.pageY - 10) + 'px');
}}).on('mouseout', () => tooltip.style('display', 'none'));

// Tick
simulation.on('tick', () => {{
  linkEl
    .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
    .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
  nodeEl.attr('transform', d => `translate(${{d.x}},${{d.y}})`);
  drawHulls();
}});

function drawHulls() {{
  const groups = {{}};
  DATA.stack_groups.forEach((sg, i) => {{
    const points = [];
    sg.pr_numbers.forEach(n => {{
      const nd = nodeMap[n];
      if (nd && nd.x != null) points.push([nd.x, nd.y]);
    }});
    if (points.length >= 3) {{
      groups[sg.group_id] = {{ points, color: hullColors[i % hullColors.length] }};
    }}
  }});
  hullG.selectAll('path').remove();
  for (const [, grp] of Object.entries(groups)) {{
    const hull = d3.polygonHull(grp.points);
    if (hull) {{
      hullG.append('path')
        .attr('d', 'M' + hull.join('L') + 'Z')
        .attr('class', 'hull')
        .attr('fill', grp.color)
        .attr('stroke', grp.color);
    }}
  }}
}}

function showSidebar(d) {{
  const sb = document.getElementById('sidebar');
  sb.classList.add('visible');
  const conflicts = DATA.edges.filter(e =>
    e.source_pr === d.pr_number || e.target_pr === d.pr_number);
  const conflictHtml = conflicts.map(e => {{
    const other = e.source_pr === d.pr_number ? e.target_pr : e.source_pr;
    return `<div class="conflict-item">
      <span class="badge badge-${{e.severity_max}}">${{e.severity_max}}</span>
      #${{other}} &mdash; ${{e.conflict_count}} conflict(s): ${{e.conflict_types.join(', ')}}
    </div>`;
  }}).join('');
  const filesHtml = d.files_changed.map(f => `<li>${{escHtml(f)}}</li>`).join('');
  const noConflicts = '<div class="detail-value" '
    + 'style="color:#64748b">None</div>';
  const aiBadge = d.ai_authored
    ? '<div class="detail-row">'
    + '<span class="badge badge-warning">'
    + 'AI Authored</span></div>' : '';
  const el = document.getElementById('sidebarContent');
  el.innerHTML = ''
    + '<h3>#' + d.pr_number + ' '
    + escHtml(d.title) + '</h3>'
    + dRow('Author', escHtml(d.author))
    + dRow('Risk Score', d.risk_score.toFixed(1))
    + dRow('Blast Radius',
        d.direct_blast + ' direct, '
        + d.transitive_blast + ' transitive')
    + dRow('Stack', d.stack_group || 'None')
    + aiBadge
    + '<div class="detail-row">'
    + '<div class="detail-label">Conflicts</div>'
    + (conflictHtml || noConflicts) + '</div>'
    + '<div class="detail-row">'
    + '<div class="detail-label">Files Changed ('
    + d.files_changed.length + ')</div>'
    + '<ul class="file-list">'
    + filesHtml + '</ul></div>';
}}

function dRow(label, value) {{
  return '<div class="detail-row">'
    + '<div class="detail-label">' + label + '</div>'
    + '<div class="detail-value">'
    + value + '</div></div>';
}}

let fileEdgeEls = [];
function showFileEdges(d) {{
  // Remove existing file edges
  fileEdgeEls.forEach(el => el.remove());
  fileEdgeEls = [];
  const relevant = DATA.file_edges.filter(fe =>
    d.files_changed.includes(fe.source) || d.files_changed.includes(fe.target));
  // Simple visual: highlight edges from this node's files
  relevant.forEach(fe => {{
    const el = g.append('line')
      .attr('x1', d.x).attr('y1', d.y).attr('x2', d.x + (Math.random()-0.5)*100)
      .attr('y2', d.y + (Math.random()-0.5)*100)
      .attr('stroke', '#8b5cf6').attr('stroke-width', 1).attr('stroke-dasharray', '2,2')
      .attr('stroke-opacity', 0.5);
    fileEdgeEls.push(el);
  }});
  // Show sidebar with file deps
  showSidebar(d);
}}

// Controls
document.getElementById('closeSidebar').onclick = () =>
  document.getElementById('sidebar').classList.remove('visible');

document.getElementById('resetBtn').onclick = () => {{
  nodeData.forEach(d => {{ d.fx = null; d.fy = null; }});
  simulation.alpha(1).restart();
  svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);
  fileEdgeEls.forEach(el => el.remove());
  fileEdgeEls = [];
}};

document.getElementById('severityFilter').onchange = function() {{
  const val = this.value;
  const minLevel = val === 'critical' ? 2 : val === 'warning' ? 1 : -1;
  linkEl.attr('display', d => _SEVERITY_ORDER[d.severity_max] >= minLevel ? null : 'none');
  nodeEl.attr('opacity', d => {{
    if (val === 'all') return 1;
    const connected = DATA.edges.some(e =>
      (e.source_pr === d.pr_number || e.target_pr === d.pr_number) &&
      _SEVERITY_ORDER[e.severity_max] >= minLevel);
    return connected || d.severity_max === val ? 1 : 0.2;
  }});
}};

const _SEVERITY_ORDER = {{ critical: 2, warning: 1, info: 0, none: -1 }};

document.getElementById('toggleIntraStack').onchange = function() {{
  linkEl.attr('display', d => {{
    if (!this.checked && d.is_intra_stack) return 'none';
    return null;
  }});
}};

document.getElementById('searchPR').oninput = function() {{
  const q = this.value.replace('#', '').trim();
  if (!q) {{ nodeEl.attr('opacity', 1); linkEl.attr('opacity', 0.6); return; }}
  const num = parseInt(q, 10);
  nodeEl.attr('opacity', d => d.pr_number === num ? 1 : 0.15);
  linkEl.attr('opacity', d => {{
    const src = typeof d.source === 'object' ? d.source.id : d.source;
    const tgt = typeof d.target === 'object' ? d.target.id : d.target;
    return src === num || tgt === num ? 0.8 : 0.05;
  }});
}};

function escHtml(s) {{
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}}
</script>
</body>
</html>"""
