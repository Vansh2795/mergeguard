# Phase 1 — Week 6: CLI + Documentation + Launch

## Goals
- Polish CLI, write documentation, prepare for MVP launch

## Daily Tasks

### Day 1-2: CLI Implementation
- [x] Implement `analyze` command with all options
- [x] Implement `map` command (collision matrix)
- [x] Implement `dashboard` command (risk scores for all PRs)
- [x] Add `--version` flag
- [x] Rich terminal output with color-coded tables

### Day 3-4: Documentation
- [x] Write getting-started.md (5-minute setup guide)
- [x] Write how-it-works.md (architecture overview)
- [x] Write configuration.md (all config options)
- [x] Write contributing.md (dev setup, testing, PR guidelines)

### Day 5: Launch Preparation
- [ ] Dogfood: run MergeGuard on its own repo
- [ ] Record demo showing conflicting AI PRs being caught
- [ ] Write Show HN post draft
- [ ] Publish to PyPI: `uv build && uv publish`
- [ ] Submit to GitHub Marketplace

## Deliverables
- [x] Polished CLI with 3 commands
- [x] Complete documentation (4 pages)
- [ ] Published to PyPI
- [ ] GitHub Action on Marketplace

## Acceptance Criteria
- [x] `mergeguard analyze` produces correct output for test repos
- [x] `mergeguard map` shows collision matrix
- [x] `mergeguard dashboard` shows risk scores
- [x] Documentation is clear and complete
- [ ] MVP launched
