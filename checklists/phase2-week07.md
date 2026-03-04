# Phase 2 — Week 7: Risk Scoring System (Part 1)

## Goals
- Implement conflict severity scoring and blast radius calculation

## Daily Tasks

### Day 1-2: Conflict Severity Scoring
- [x] Implement `_score_conflicts()` with diminishing returns
- [x] Critical = 100, Warning = 50, Info = 15
- [x] Multiple conflicts add diminishing value (0.5^n)
- [x] Write tests for all severity combinations

### Day 3-4: Blast Radius
- [x] Implement dependency graph builder in dependency.py
- [x] Extract Python/JS/Go import statements
- [x] Build adjacency list (forward and reverse)
- [x] Implement `get_dependents()` with BFS
- [x] Compute `dependency_depth()` for blast radius score

### Day 5: Integration
- [x] Wire blast radius into risk scorer
- [x] Test with realistic dependency graphs
- [x] Verify blast radius score scales correctly

## Deliverables
- [x] Conflict severity scoring with diminishing returns
- [x] Import graph builder for Python, JS, Go
- [x] Blast radius calculation via BFS

## Acceptance Criteria
- [x] Single critical conflict scores 100
- [x] Multiple conflicts have diminishing contributions
- [x] Blast radius increases with dependency depth
