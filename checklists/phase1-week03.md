# Phase 1 — Week 3: Tree-sitter AST Integration

## Goals
- Parse source files and extract function/class/method boundaries with line ranges

## Daily Tasks

### Day 1-3: AST Parser
- [ ] Implement language detection from file extensions
- [ ] Write Tree-sitter query patterns for Python, TypeScript, JavaScript, Go
- [ ] Implement `extract_symbols()` — parse source and return Symbol list
- [ ] Implement `map_diff_to_symbols()` — map line ranges to affected symbols
- [ ] Create fallback regex-based extraction for unsupported languages
- [ ] Handle edge cases: anonymous functions, nested classes, decorators

### Day 4-5: Symbol Index + Tests
- [ ] Build `SymbolIndex` class with caching by (file_path, ref)
- [ ] Implement `find_symbol()` and `find_callers()`
- [ ] Write tests with known Python, TypeScript, Go source files
- [ ] Verify map_diff_to_symbols correctly identifies affected functions

## Deliverables
- [ ] Working AST parser for Python, JS/TS, and Go
- [ ] Symbol index with caching
- [ ] Regex fallback for unsupported languages

## Acceptance Criteria
- [ ] extract_symbols returns correct symbols for test Python files
- [ ] map_diff_to_symbols correctly maps line ranges to function names
- [ ] SymbolIndex caching works (same file+ref returns cached result)
