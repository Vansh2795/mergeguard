# MergeGuard Roadmap

Public-facing roadmap for MergeGuard development.

## v0.2 — Accuracy & Core :white_check_mark:

Focus: dramatically improve conflict detection accuracy and complete core features.

- :white_check_mark: **Cross-file symbol resolution** — Detect conflicts between PRs that touch different files linked by imports. Unlocks ~70%+ of real-world conflicts.
- :white_check_mark: **Cross-file call graph** — Extend call graph analysis beyond single files to detect behavioral conflicts across module boundaries.
- :white_check_mark: **Configurable risk weights** — Allow teams to tune risk scoring factors via `.mergeguard.yml` instead of using hardcoded defaults.
- :white_check_mark: **Complete guardrail rules** — All 6 rule types: `cannot_import_from`, `must_not_contain`, `max_function_lines`, `max_cyclomatic_complexity`, `max_files_changed`, and `max_lines_changed`.
- :white_check_mark: **Remove transitive conflict cap** — Show the full blast radius instead of limiting to 1 transitive conflict per PR pair. Configurable via `max_transitive_per_pair`.
- :white_check_mark: **Diff preview in terminal** — Show actual conflicting code in terminal output with Rich syntax highlighting.
- :white_check_mark: **Holistic LLM analysis** — Analyze all conflicts for a PR pair in a single LLM call to identify related conflicts and provide better recommendations.
- :white_check_mark: **PyYAML as core dependency** — Reliable config parsing for nested structures.

## v0.3 — Enterprise Ready :white_check_mark:

Focus: platform support and enterprise workflow features.

- :white_check_mark: **GitHub Enterprise Server** — Support self-hosted GitHub instances via `--github-url` config.
- :white_check_mark: **Bitbucket Cloud** — New integration via Bitbucket REST API 2.0.
- :white_check_mark: **Multi-repo analysis** — Detect conflicts across repositories that share dependencies (`mergeguard analyze-multi`).
- :white_check_mark: **Merge order suggestion** — Topological sort on conflict graph to suggest optimal merge sequence (`mergeguard suggest-order`).
- :white_check_mark: **Watch mode** — Continuously monitor PRs and auto-post comments when conflicts are detected (`mergeguard watch`).
- :white_check_mark: **Configurable constants** — Expose all performance limits (file size, diff size, timeouts, workers) via config.
- :white_check_mark: **Historical analysis / audit trail** — Track analysis results over time for trend reporting (`mergeguard history`).

## v0.4 — Community & Ecosystem :white_check_mark:

Focus: integrations, reporting, and developer experience.

- :white_check_mark: **MCP server** — Full implementation of `check_conflicts`, `get_risk_score`, and `suggest_merge_order` tools for AI agent integration. Enables preventive conflict detection before PRs are created.
- :white_check_mark: **HTML report** — Self-contained HTML output with risk gauges, sortable tables, and syntax-highlighted diffs (`--format html`).
- :white_check_mark: **Slack/Teams notifications** — Post conflict summaries via webhooks on critical/warning findings.
- :white_check_mark: **`mergeguard init` wizard** — Interactive setup that detects your stack and generates a tailored config.
- :white_check_mark: **Static web dashboard** — Single HTML file with Chart.js visualizations, deployable to GitHub Pages (`mergeguard dashboard --format html`).

## v0.5 — Enterprise Workflows (In Progress)

Focus: real-time workflows, inline developer experience, and deployment infrastructure.

- :white_check_mark: **Inline PR annotations** — Line-level conflict warnings posted directly on PR diffs (GitHub, GitLab, Bitbucket review APIs)
- :white_check_mark: **Webhook-driven real-time analysis** — Instant conflict detection on PR open/update/close via webhook server
- :white_check_mark: **CODEOWNERS-aware routing** — Route conflict notifications to file owners
- :white_check_mark: **Merge queue integration** — Conflict-aware merge ordering with commit status checks and priority overrides
- :white_check_mark: **Stacked PR support** — Detect stacked PR groups, demote intra-stack conflicts, stack-aware merge ordering
- :calendar: **Blast radius visualization** — Interactive dependency graph showing conflict impact
- :calendar: **Policy engine** — Customizable merge policies based on conflict analysis
- :calendar: **DORA metrics** — Track conflict resolution time and merge frequency
- :calendar: **Secret scanning** — Detect accidentally committed secrets in PR diffs
- :calendar: **Self-hosted runner** — On-prem deployment option
- :calendar: **AI conflict resolution** — LLM-powered merge conflict resolution suggestions
- :calendar: **IDE integration** — VS Code extension for real-time conflict warnings
- :calendar: **Service mesh awareness** — Cross-service conflict detection for microservices

---

*This roadmap is subject to change based on community feedback. Have a feature request? [Open an issue](https://github.com/Vansh2795/mergeguard/issues/new?template=feature_request.yml).*
