#!/bin/bash
set -euo pipefail

# Extract PR number from GitHub event
PR_NUMBER=$(jq -r '.pull_request.number' "$GITHUB_EVENT_PATH")
REPO_FULL_NAME=$(jq -r '.repository.full_name' "$GITHUB_EVENT_PATH")

# Run MergeGuard
uv run mergeguard analyze \
  --repo "$REPO_FULL_NAME" \
  --pr "$PR_NUMBER" \
  --token "$GITHUB_TOKEN" \
  --config "$MERGEGUARD_CONFIG_PATH" \
  --format github-action

# Capture outputs for GitHub Actions
echo "risk-score=$(cat /tmp/mergeguard-score.txt)" >> "$GITHUB_OUTPUT"
echo "conflict-count=$(cat /tmp/mergeguard-conflicts.txt)" >> "$GITHUB_OUTPUT"
