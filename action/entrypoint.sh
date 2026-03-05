#!/bin/bash
set -euo pipefail

# Extract PR number and repo from GitHub event
PR_NUMBER=$(jq -r '.pull_request.number' "$GITHUB_EVENT_PATH")
REPO_FULL_NAME=$(jq -r '.repository.full_name' "$GITHUB_EVENT_PATH")

# Build CLI arguments
ARGS="--repo $REPO_FULL_NAME --pr $PR_NUMBER --format json"

if [ -n "${MERGEGUARD_CONFIG_PATH:-}" ]; then
  ARGS="$ARGS --config $MERGEGUARD_CONFIG_PATH"
fi

# Run MergeGuard and capture JSON output
REPORT=$(uv run mergeguard analyze $ARGS)

# Extract outputs from JSON
RISK_SCORE=$(echo "$REPORT" | jq -r '.risk_score')
CONFLICT_COUNT=$(echo "$REPORT" | jq -r '.conflicts | length')

# Write outputs for downstream steps
echo "risk-score=$RISK_SCORE" >> "$GITHUB_OUTPUT"
echo "conflict-count=$CONFLICT_COUNT" >> "$GITHUB_OUTPUT"
echo "report-json=$REPORT" >> "$GITHUB_OUTPUT"

# Post PR comment if risk exceeds threshold
THRESHOLD="${INPUT_RISK_THRESHOLD:-0}"
if [ "$RISK_SCORE" -ge "$THRESHOLD" ]; then
  uv run mergeguard analyze \
    --repo "$REPO_FULL_NAME" \
    --pr "$PR_NUMBER" \
    --post-comment
fi

# Fail the check if risk exceeds threshold and fail-on-risk is set
if [ "${INPUT_FAIL_ON_RISK:-false}" = "true" ] && [ "$RISK_SCORE" -ge "$THRESHOLD" ]; then
  echo "::error::MergeGuard risk score ($RISK_SCORE) exceeds threshold ($THRESHOLD)"
  exit 1
fi
