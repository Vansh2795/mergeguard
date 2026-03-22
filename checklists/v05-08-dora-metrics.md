# v0.5 — Feature 08: Historical Trends & DORA Metrics

## Goals
- Track conflict analysis results over time in a persistent store
- Surface trend data: conflict frequency, resolution time, team hotspots, recurring file pairs
- Export metrics in Prometheus format for Grafana integration and correlate with DORA metrics

## Daily Tasks

### Day 1-2: Metrics Storage
- [ ] Extend `storage/decisions_log.py` SQLite schema with `analysis_history` table
- [ ] Schema: `id`, `repo`, `pr_number`, `analyzed_at`, `risk_score`, `conflict_count`, `conflicts_json`, `severity_counts`, `analysis_duration_ms`
- [ ] Add `record_analysis(report: ConflictReport, repo: str, duration_ms: int)` method
- [ ] Add `conflict_pairs` table: `file_a`, `file_b`, `conflict_type`, `count`, `last_seen` for hotspot tracking
- [ ] Wire recording into `core/engine.py` — store results after every analysis run
- [ ] Add data retention config: `metrics.retention_days` (default: 90)

### Day 3: Trend Queries & Aggregation
- [ ] Implement `get_conflict_trend(repo: str, period_days: int) -> list[DailyMetric]` — conflicts per day
- [ ] Implement `get_hotspot_pairs(repo: str, limit: int) -> list[tuple[str, str, int]]` — most conflicting file pairs
- [ ] Implement `get_team_hotspots(repo: str) -> dict[str, int]` — conflict count by team (requires CODEOWNERS integration)
- [ ] Implement `get_resolution_time(repo: str) -> float` — average time between conflict detection and PR merge
- [ ] Create `MetricsSummary` Pydantic model for API/CLI consumption

### Day 4: CLI & Dashboard
- [ ] Add `mergeguard metrics` CLI command with `--period`, `--repo`, `--format` (table/json/csv) options
- [ ] Display trend table in terminal: week-over-week conflict count, risk score average, top hotspots
- [ ] Add trend charts page to `output/dashboard_html.py` using Chart.js (line chart for conflicts/week, bar chart for hotspots)
- [ ] Show DORA correlation panel: map conflict frequency against deployment frequency and change failure rate
- [ ] Add sparkline trend to existing PR comment summary: "Conflicts trending ↑12% this week"

### Day 5: Prometheus Export & Testing
- [ ] Add `/metrics` endpoint to webhook server (`server/webhook.py`) in Prometheus exposition format
- [ ] Export: `mergeguard_conflicts_total{repo, severity}`, `mergeguard_risk_score{repo}`, `mergeguard_analysis_duration_seconds{repo}`
- [ ] Export: `mergeguard_hotspot_conflicts{file_a, file_b}` (top 20 pairs only)
- [ ] Test with 1000+ historical data points — verify query performance under 500ms
- [ ] Test data retention cleanup (auto-purge records older than retention_days)
- [ ] Verify trend calculations match manual counts

## Deliverables
- [ ] Extended SQLite schema with `analysis_history` and `conflict_pairs` tables
- [ ] Trend query API: `get_conflict_trend()`, `get_hotspot_pairs()`, `get_team_hotspots()`
- [ ] `mergeguard metrics` CLI command
- [ ] Chart.js trend visualizations in HTML dashboard
- [ ] Prometheus metrics endpoint

## Acceptance Criteria
- [ ] Every analysis run recorded in SQLite with full conflict data
- [ ] `mergeguard metrics --period 30d` shows conflict trends, top hotspots, and average risk scores
- [ ] Dashboard trend page renders line/bar charts with selectable time ranges
- [ ] Prometheus endpoint scraped successfully by Prometheus/Grafana
- [ ] Data retention auto-purge keeps database size manageable
- [ ] Queries return in under 500ms for 90 days of data across 10 repos

> **Extend:** `storage/decisions_log.py` (new tables and queries), `core/engine.py` (record analysis), `output/dashboard_html.py` (trend charts), `cli.py` (metrics command), `server/webhook.py` (Prometheus endpoint), `models.py` (MetricsSummary model), `config.py` (metrics config section).
