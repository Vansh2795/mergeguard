# Phase 3 — Week 16: Dashboard (Part 2) — Trends & Merge Order

## Goals
- Add risk trends and merge order suggestions to dashboard

## Daily Tasks

### Day 1-2: Risk Score Trends
- [ ] Store historical risk scores in SQLite
- [ ] Implement Recharts line chart for trends over time
- [ ] Show per-PR risk score evolution
- [ ] Show repo-wide risk score average

### Day 3-4: Merge Order Suggestions
- [ ] Implement topological sort on conflict graph
- [ ] Suggest optimal merge order (minimize conflicts)
- [ ] Display suggested order in dashboard
- [ ] Explain reasoning for each suggestion

### Day 5: Polish + Testing
- [ ] End-to-end testing of dashboard
- [ ] Performance optimization (lazy loading, pagination)
- [ ] Documentation for dashboard setup

## Deliverables
- [ ] Risk score trend charts
- [ ] Merge order suggestion algorithm
- [ ] Complete dashboard feature set

## Acceptance Criteria
- [ ] Trends show accurate historical data
- [ ] Merge order reduces total conflicts when followed
- [ ] Dashboard performs well with 30 open PRs
