# Phase 3 — Week 18: MCP Server (Part 2) — Merge Order + Polish

## Goals
- Complete MCP server with merge order tool and polish

## Daily Tasks

### Day 1-2: Merge Order Tool
- [ ] Implement `suggest_merge_order` MCP tool
- [ ] Return ordered list with conflict reasoning
- [ ] Support filtering by labels/authors

### Day 3-4: MCP Polish
- [ ] Add progress notifications for long-running analysis
- [ ] Implement caching for repeated queries
- [ ] Add documentation for MCP setup
- [ ] Support both stdio and SSE transport

### Day 5: Integration Testing
- [ ] Test full workflow: AI agent → check conflicts → open PR
- [ ] Test with multiple concurrent AI agents
- [ ] Performance testing under load

## Deliverables
- [ ] Complete MCP server with 3 tools
- [ ] MCP documentation and setup guide
- [ ] Performance benchmarks

## Acceptance Criteria
- [ ] All 3 MCP tools working reliably
- [ ] Responds within 10 seconds for typical queries
- [ ] Works with Claude Desktop and other MCP clients
