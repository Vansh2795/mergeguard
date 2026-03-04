# Phase 1 — Week 3: Tree-sitter AST Integration

## Goals
- Parse source files and extract function/class/method boundaries with line ranges

## Daily Tasks

### Day 1-3: AST Parser
- [x] Implement language detection from file extensions
- [x] Write Tree-sitter query patterns for Python, TypeScript, JavaScript, Go
- [x] Implement `extract_symbols()` — parse source and return Symbol list
- [x] Implement `map_diff_to_symbols()` — map line ranges to affected symbols
- [x] Create fallback regex-based extraction for unsupported languages
- [x] Handle edge cases: anonymous functions, nested classes, decorators

### Day 4-5: Symbol Index + Tests
- [x] Build `SymbolIndex` class with caching by (file_path, ref)
- [x] Implement `find_symbol()` and `find_callers()`
- [x] Write tests with known Python, TypeScript, Go source files
- [x] Verify map_diff_to_symbols correctly identifies affected functions

## Deliverables
- [x] Working AST parser for Python, JS/TS, and Go
- [x] Symbol index with caching
- [x] Regex fallback for unsupported languages

## Acceptance Criteria
- [x] extract_symbols returns correct symbols for test Python files
- [x] map_diff_to_symbols correctly maps line ranges to function names
- [x] SymbolIndex caching works (same file+ref returns cached result)
