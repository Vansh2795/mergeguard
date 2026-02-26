# Phase 2 — Week 9: Decisions Log (SQLite)

## Goals
- Implement SQLite-backed decisions log for tracking merge history

## Daily Tasks

### Day 1-2: Database Schema + CRUD
- [ ] Create SQLite database with decisions table
- [ ] Implement `record_merge()` — store decisions from merged PRs
- [ ] Implement `get_recent_decisions()` — retrieve for regression checking
- [ ] Add index on merged_at for performance
- [ ] Handle database creation and migrations

### Day 3-4: Decision Extraction
- [ ] Detect REMOVAL decisions (functions/classes deleted)
- [ ] Detect MIGRATION decisions (pattern A → pattern B)
- [ ] Detect ADDITION decisions (new patterns introduced)
- [ ] Extract decisions from diff analysis

### Day 5: Integration + Testing
- [ ] Wire decisions log into the engine
- [ ] Test with simulated merge history
- [ ] Verify decisions persist across runs (SQLite file)
- [ ] Test database recovery from corruption

## Deliverables
- [ ] SQLite-backed decisions log
- [ ] Decision extraction from merged PRs
- [ ] Persistent storage in .mergeguard-cache/

## Acceptance Criteria
- [ ] Decisions survive across CI runs (with cache action)
- [ ] Recent decisions retrieved in correct order
- [ ] Database handles concurrent access gracefully
