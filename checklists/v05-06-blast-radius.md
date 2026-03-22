# v0.5 — Feature 06: Blast Radius Visualization

## Goals
- Show the full transitive impact of each conflict: how many downstream files, symbols, and services are affected
- Generate interactive dependency graphs for the HTML dashboard
- Surface blast radius as a numeric score in PR comments

## Daily Tasks

### Day 1-2: Extended Dependency Graph
- [ ] Extend `analysis/dependency.py` `DependencyGraph` to full repo scope (not just changed files)
- [ ] Add `get_transitive_dependents(symbol: str, max_depth: int = 10) -> list[str]` method
- [ ] Add `get_blast_radius(files: list[str]) -> BlastRadius` returning affected files, symbols, depth
- [ ] Create `BlastRadius` model in `models.py`: `affected_files: int`, `affected_symbols: int`, `max_depth: int`, `affected_paths: list[str]`
- [ ] Cache full-repo dependency graph in `storage/cache.py` (invalidate on new commits)
- [ ] Optimize for large repos: lazy loading, limit traversal depth

### Day 3: Blast Radius in Conflict Reports
- [ ] Add `blast_radius: BlastRadius | None` field to `Conflict` model
- [ ] Compute blast radius during conflict classification in `core/conflict.py`
- [ ] Factor blast radius into `core/risk_scorer.py` — high blast radius increases risk score
- [ ] Update existing `dependency_depth` factor in risk scorer to use full `BlastRadius` data
- [ ] Add blast radius to `output/json_report.py` serialization

### Day 4: D3.js / Mermaid Visualization
- [ ] Add dependency graph visualization to `output/dashboard_html.py`
- [ ] Render as D3.js force-directed graph with conflict nodes highlighted in red
- [ ] Node size proportional to blast radius
- [ ] Clickable nodes: show file path, owning symbols, and downstream count
- [ ] Alternative Mermaid diagram output for PR comments (static, renders on GitHub)
- [ ] Add `--blast-radius` flag to `mergeguard analyze` CLI command

### Day 5: PR Comment Integration & Testing
- [ ] Update `output/github_comment.py` to include blast radius: "This conflict affects N downstream files across M packages"
- [ ] Add Mermaid dependency subgraph in collapsible section of PR comment
- [ ] Test with large repos (1000+ files) — ensure graph rendering stays under 5 seconds
- [ ] Test circular dependency handling (break cycles, warn in output)
- [ ] Verify blast radius calculation matches manual import tracing

## Deliverables
- [ ] Extended `DependencyGraph` with full-repo transitive analysis
- [ ] `BlastRadius` model and integration into conflict reports
- [ ] D3.js interactive graph in HTML dashboard
- [ ] Mermaid diagram in PR comments
- [ ] Blast radius numeric score in conflict summaries

## Acceptance Criteria
- [ ] Blast radius calculated for every conflict with dependency information
- [ ] Dashboard shows interactive force-directed graph with conflict highlighting
- [ ] PR comments show blast radius as "affects N files, M symbols"
- [ ] Full-repo graph builds in under 10 seconds for repos with <5000 files
- [ ] Circular dependencies handled gracefully (cycle broken, warning shown)
- [ ] Blast radius factors into risk score calculation

> **Extend:** `analysis/dependency.py` (full-repo graph, `get_blast_radius()`), `models.py` (BlastRadius model, field on Conflict), `core/conflict.py` (compute blast radius), `core/risk_scorer.py` (factor into score), `output/dashboard_html.py` (D3.js graph), `output/github_comment.py` (blast radius text + Mermaid), `output/json_report.py` (serialization), `cli.py` (--blast-radius flag).
