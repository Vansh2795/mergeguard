# Phase 3 — Week 17: MCP Server (Part 1)

## Goals
- Expose MergeGuard as an MCP server for AI agent integration

## Daily Tasks

### Day 1-2: MCP Server Setup
- [x] Set up MCP server framework
- [ ] Implement `check_conflicts` tool
- [x] Define input/output schemas
- [x] Handle authentication (GitHub token passing)

### Day 3-4: Risk Score Tool
- [ ] Implement `get_risk_score` tool
- [ ] Return score breakdown
- [ ] Support hypothetical analysis (files not yet committed)

### Day 5: Testing
- [ ] Test MCP tools with mock data
- [ ] Test with Claude Desktop as MCP client
- [ ] Verify JSON-RPC compliance

## Deliverables
- [ ] MCP server with check_conflicts and get_risk_score tools
- [ ] Working with Claude Desktop

## Acceptance Criteria
- [ ] AI agents can check conflicts before opening PRs
- [ ] Risk scores returned within 5 seconds
- [ ] Clean error handling for invalid inputs

> **Note:** `mcp/server.py` exists with `create_mcp_server()` but all tools currently return `"not_implemented"`. Framework is in place, tool logic needs to be connected.
