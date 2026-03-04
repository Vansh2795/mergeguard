# Phase 2 — Week 11: Optional LLM Integration

## Goals
- Add Claude-powered semantic analysis for behavioral conflicts

## Daily Tasks

### Day 1-2: LLM Analyzer
- [x] Implement `LLMAnalyzer` class with Anthropic SDK
- [x] Design prompt for behavioral conflict analysis
- [x] Parse structured JSON response from Claude
- [x] Handle API errors gracefully
- [x] Implement token cost management (truncate large diffs)

### Day 3-4: Integration
- [x] Wire LLM analyzer into conflict detection pipeline
- [x] Only invoke LLM for behavioral conflicts (same function, different lines)
- [x] Respect `llm_enabled` config flag
- [x] Lazy import anthropic package
- [x] Clear error message when anthropic not installed

### Day 5: Testing
- [x] Test with mocked Anthropic API responses
- [x] Test graceful degradation when LLM unavailable
- [x] Test token cost estimation
- [x] Verify LLM results properly classified as conflicts

## Deliverables
- [x] LLM-powered behavioral conflict analysis
- [x] Optional dependency (works without anthropic installed)
- [x] Mocked integration tests

## Acceptance Criteria
- [x] LLM analysis only runs when llm_enabled=true
- [x] Behavioral conflicts get upgraded/downgraded severity based on LLM
- [x] Works cleanly without anthropic package installed

> **Note:** `LLMAnalyzer` is fully implemented in `integrations/llm_analyzer.py` and wired into the engine via `_apply_llm_analysis()` (Gap #10 fixed). Gated by `llm_enabled` config and `ANTHROPIC_API_KEY` env var.
