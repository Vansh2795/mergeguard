# Phase 2 — Week 7: Risk Scoring System (Part 1)

## Goals
- Implement conflict severity scoring and blast radius calculation

## Daily Tasks

### Day 1-2: Conflict Severity Scoring
- [ ] Implement `_score_conflicts()` with diminishing returns
- [ ] Critical = 100, Warning = 50, Info = 15
- [ ] Multiple conflicts add diminishing value (0.5^n)
- [ ] Write tests for all severity combinations

### Day 3-4: Blast Radius
- [ ] Implement dependency graph builder in dependency.py
- [ ] Extract Python/JS/Go import statements
- [ ] Build adjacency list (forward and reverse)
- [ ] Implement `get_dependents()` with BFS
- [ ] Compute `dependency_depth()` for blast radius score

### Day 5: Integration
- [ ] Wire blast radius into risk scorer
- [ ] Test with realistic dependency graphs
- [ ] Verify blast radius score scales correctly

## Deliverables
- [ ] Conflict severity scoring with diminishing returns
- [ ] Import graph builder for Python, JS, Go
- [ ] Blast radius calculation via BFS

## Acceptance Criteria
- [ ] Single critical conflict scores 100
- [ ] Multiple conflicts have diminishing contributions
- [ ] Blast radius increases with dependency depth
