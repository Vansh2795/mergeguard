# Phase 2 — Week 11: Optional LLM Integration

## Goals
- Add Claude-powered semantic analysis for behavioral conflicts

## Daily Tasks

### Day 1-2: LLM Analyzer
- [ ] Implement `LLMAnalyzer` class with Anthropic SDK
- [ ] Design prompt for behavioral conflict analysis
- [ ] Parse structured JSON response from Claude
- [ ] Handle API errors gracefully
- [ ] Implement token cost management (truncate large diffs)

### Day 3-4: Integration
- [ ] Wire LLM analyzer into conflict detection pipeline
- [ ] Only invoke LLM for behavioral conflicts (same function, different lines)
- [ ] Respect `llm_enabled` config flag
- [ ] Lazy import anthropic package
- [ ] Clear error message when anthropic not installed

### Day 5: Testing
- [ ] Test with mocked Anthropic API responses
- [ ] Test graceful degradation when LLM unavailable
- [ ] Test token cost estimation
- [ ] Verify LLM results properly classified as conflicts

## Deliverables
- [ ] LLM-powered behavioral conflict analysis
- [ ] Optional dependency (works without anthropic installed)
- [ ] Mocked integration tests

## Acceptance Criteria
- [ ] LLM analysis only runs when llm_enabled=true
- [ ] Behavioral conflicts get upgraded/downgraded severity based on LLM
- [ ] Works cleanly without anthropic package installed
