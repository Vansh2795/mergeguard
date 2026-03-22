# v0.5 — Feature 12: IDE Integration (VS Code + JetBrains)

## Goals
- Catch conflicts before pushing by showing real-time conflict warnings in the editor
- Use the MCP server as the backend for IDE communication
- Provide lightweight, file-scoped analysis that doesn't slow down the editor

## Daily Tasks

### Day 1-2: VS Code Extension Scaffold
- [ ] Create `ide/vscode/` directory with extension scaffold (package.json, tsconfig, webpack config)
- [ ] Define extension activation: activate on workspace open if `.mergeguard.yml` exists or git remote detected
- [ ] Implement MCP client connection to `mcp/server.py` backend
- [ ] Implement file-scoped analysis: on file save, send changed symbols to MCP `check_conflicts` tool
- [ ] Display results as VS Code diagnostics (squiggly underlines) with severity mapping: CRITICAL → Error, WARNING → Warning, INFO → Information

### Day 3: VS Code UX
- [ ] Add editor gutter decorations: conflict indicator icons on affected lines
- [ ] Add hover provider: hovering over a conflicting symbol shows conflict details and link to the conflicting PR
- [ ] Add code action: "Open conflicting PR" quick action that opens the PR URL in browser
- [ ] Add code action: "Show all conflicts" that opens a panel with full conflict list
- [ ] Add status bar item: conflict count badge (e.g., "MergeGuard: 2 conflicts")
- [ ] Add extension settings: `mergeguard.serverUrl`, `mergeguard.token`, `mergeguard.autoAnalyze` (on save vs manual)

### Day 4: JetBrains Plugin
- [ ] Create `ide/jetbrains/` directory with Gradle plugin scaffold (plugin.xml, build.gradle.kts)
- [ ] Implement MCP client connection (reuse protocol, implement in Kotlin)
- [ ] Add external annotator for gutter icons on conflicting lines
- [ ] Add inspection provider for conflict warnings in the Problems tool window
- [ ] Add intention action: "Open conflicting PR" and "Show MergeGuard conflicts"
- [ ] Add tool window panel: full conflict list with filtering and sorting

### Day 5: Performance & Testing
- [ ] Implement debouncing: wait 2 seconds after last edit before re-analyzing (avoid excessive API calls)
- [ ] Implement caching: only re-analyze when symbols in the current file actually changed
- [ ] Test VS Code extension with mock MCP server
- [ ] Test JetBrains plugin with mock MCP server
- [ ] Ensure MCP server handles concurrent IDE connections (multiple developers on same repo)
- [ ] Package VS Code extension as .vsix, JetBrains plugin as .zip
- [ ] Document installation and configuration for both IDEs

## Deliverables
- [ ] VS Code extension (`ide/vscode/`) with diagnostics, gutter icons, hover, and code actions
- [ ] JetBrains plugin (`ide/jetbrains/`) with annotator, inspections, and intentions
- [ ] MCP client integration for real-time conflict checking
- [ ] Extension packaging and installation documentation

## Acceptance Criteria
- [ ] VS Code shows squiggly underlines on lines that conflict with open PRs
- [ ] Hovering over a conflict shows the conflicting PR number, title, and conflict type
- [ ] "Open conflicting PR" action opens the correct PR URL in browser
- [ ] Analysis runs in under 2 seconds for single-file scope
- [ ] No noticeable editor lag — analysis runs in background
- [ ] Works with MCP server running locally or remotely
- [ ] Both extensions installable from packaged artifacts

> **Extend:** `mcp/server.py` (ensure `check_conflicts` tool supports single-file scope, concurrent connections). **New:** `ide/vscode/` (VS Code extension), `ide/jetbrains/` (JetBrains plugin).
