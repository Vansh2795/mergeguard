#!/bin/bash
set -euo pipefail

# If running against the mergeguard repo itself (dogfood), install from local source
# to pick up unreleased fixes. Otherwise use the pre-installed PyPI version.
if grep -q 'name = "py-mergeguard"' /github/workspace/pyproject.toml 2>/dev/null; then
  pip install --no-cache-dir /github/workspace >/dev/null 2>&1
fi

# Extract PR number and repo from GitHub event
PR_NUMBER=$(jq -r '.pull_request.number' "$GITHUB_EVENT_PATH")
REPO_FULL_NAME=$(jq -r '.repository.full_name' "$GITHUB_EVENT_PATH")

# Build CLI arguments
ARGS="--repo $REPO_FULL_NAME --pr $PR_NUMBER --format json"

if [ -n "${MERGEGUARD_CONFIG_PATH:-}" ]; then
  ARGS="$ARGS --config $MERGEGUARD_CONFIG_PATH"
fi

# Run MergeGuard and capture JSON output
REPORT=$(mergeguard analyze $ARGS)

# Extract outputs from JSON (truncate float score to integer for bash comparison)
RISK_SCORE=$(echo "$REPORT" | jq -r '.risk_score')
RISK_SCORE_INT=$(echo "$RISK_SCORE" | awk '{printf "%d", $1}')
CONFLICT_COUNT=$(echo "$REPORT" | jq -r '.conflicts | length')

# Write scalar outputs
echo "risk-score=$RISK_SCORE" >> "$GITHUB_OUTPUT"
echo "conflict-count=$CONFLICT_COUNT" >> "$GITHUB_OUTPUT"

# Write multi-line JSON using heredoc delimiter
EOF_MARKER="EOF_$(date +%s%N)"
{
  echo "report-json<<$EOF_MARKER"
  echo "$REPORT"
  echo "$EOF_MARKER"
} >> "$GITHUB_OUTPUT"

# Post PR comment if risk exceeds threshold
THRESHOLD="${MERGEGUARD_RISK_THRESHOLD:-0}"
if [ "$RISK_SCORE_INT" -ge "$THRESHOLD" ]; then
  mergeguard analyze \
    --repo "$REPO_FULL_NAME" \
    --pr "$PR_NUMBER" \
    --post-comment
fi

# Fail the check if risk exceeds threshold and fail-on-risk is set
if [ "${INPUT_FAIL_ON_RISK:-false}" = "true" ] && [ "$RISK_SCORE_INT" -ge "$THRESHOLD" ]; then
  echo "::error::MergeGuard risk score ($RISK_SCORE) exceeds threshold ($THRESHOLD)"
  exit 1
fi
