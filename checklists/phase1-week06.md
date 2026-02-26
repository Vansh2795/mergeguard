# Phase 1 — Week 6: CLI + Documentation + Launch

## Goals
- Polish CLI, write documentation, prepare for MVP launch

## Daily Tasks

### Day 1-2: CLI Implementation
- [ ] Implement `analyze` command with all options
- [ ] Implement `map` command (collision matrix)
- [ ] Implement `dashboard` command (risk scores for all PRs)
- [ ] Add `--version` flag
- [ ] Rich terminal output with color-coded tables

### Day 3-4: Documentation
- [ ] Write getting-started.md (5-minute setup guide)
- [ ] Write how-it-works.md (architecture overview)
- [ ] Write configuration.md (all config options)
- [ ] Write contributing.md (dev setup, testing, PR guidelines)

### Day 5: Launch Preparation
- [ ] Dogfood: run MergeGuard on its own repo
- [ ] Record demo showing conflicting AI PRs being caught
- [ ] Write Show HN post draft
- [ ] Publish to PyPI: `uv build && uv publish`
- [ ] Submit to GitHub Marketplace

## Deliverables
- [ ] Polished CLI with 3 commands
- [ ] Complete documentation (4 pages)
- [ ] Published to PyPI
- [ ] GitHub Action on Marketplace

## Acceptance Criteria
- [ ] `mergeguard analyze` produces correct output for test repos
- [ ] `mergeguard map` shows collision matrix
- [ ] `mergeguard dashboard` shows risk scores
- [ ] Documentation is clear and complete
- [ ] MVP launched 🚀
