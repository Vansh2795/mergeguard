# Phase 2 — Week 9: Decisions Log (SQLite)

## Goals
- Implement SQLite-backed decisions log for tracking merge history

## Daily Tasks

### Day 1-2: Database Schema + CRUD
- [x] Create SQLite database with decisions table
- [x] Implement `record_merge()` — store decisions from merged PRs
- [x] Implement `get_recent_decisions()` — retrieve for regression checking
- [x] Add index on merged_at for performance
- [x] Handle database creation and migrations

### Day 3-4: Decision Extraction
- [x] Detect REMOVAL decisions (functions/classes deleted)
- [x] Detect MIGRATION decisions (pattern A → pattern B)
- [x] Detect ADDITION decisions (new patterns introduced)
- [x] Extract decisions from diff analysis

### Day 5: Integration + Testing
- [x] Wire decisions log into the engine
- [x] Test with simulated merge history
- [x] Verify decisions persist across runs (SQLite file)
- [x] Test database recovery from corruption

## Deliverables
- [x] SQLite-backed decisions log
- [x] Decision extraction from merged PRs
- [x] Persistent storage in .mergeguard-cache/

## Acceptance Criteria
- [x] Decisions survive across CI runs (with cache action)
- [x] Recent decisions retrieved in correct order
- [x] Database handles concurrent access gracefully

> **Note:** `DecisionsLog` is fully implemented in `storage/decisions_log.py` and wired into the engine (Gap #13 fixed).
