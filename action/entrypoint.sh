#!/bin/bash
set -euo pipefail

# If running against the mergeguard repo itself (dogfood), install from local source
# to pick up unreleased fixes. Otherwise use the pre-installed PyPI version.
if grep -q 'name = "py-mergeguard"' /github/workspace/pyproject.toml 2>/dev/null; then
  pip install --no-cache-dir /github/workspace >/dev/null 2>&1
fi

REPO_FULL_NAME=$(jq -r '.repository.full_name' "$GITHUB_EVENT_PATH")

# Global options (before subcommand)
GLOBAL_OPTS="--platform github"
if [ -n "${MERGEGUARD_GITHUB_URL:-}" ]; then
  GLOBAL_OPTS="$GLOBAL_OPTS --github-url ${MERGEGUARD_GITHUB_URL}"
fi

# ── Merge group event handling ──────────────────────────────────────
if [ "${GITHUB_EVENT_NAME:-}" = "merge_group" ]; then
  HEAD_SHA=$(jq -r '.merge_group.head_sha' "$GITHUB_EVENT_PATH")
  # Extract PR numbers from head_ref and commit message
  HEAD_REF=$(jq -r '.merge_group.head_ref // ""' "$GITHUB_EVENT_PATH")
  COMMIT_MSG=$(jq -r '.merge_group.head_commit.message // ""' "$GITHUB_EVENT_PATH")
  PR_NUMBERS=$(echo "$HEAD_REF $COMMIT_MSG" | grep -oE '(pr-|#)([0-9]+)' | grep -oE '[0-9]+' | sort -u)

  MERGE_QUEUE_ENABLED="${MERGEGUARD_MERGE_QUEUE:-false}"
  BLOCK_SEVERITY="${MERGEGUARD_BLOCK_SEVERITY:-critical}"
  STATUS_CONTEXT="mergeguard/cross-pr-analysis"
  API_URL="https://api.github.com"
  if [ -n "${MERGEGUARD_GITHUB_URL:-}" ]; then
    API_URL="${MERGEGUARD_GITHUB_URL}/api/v3"
  fi

  post_status() {
    local sha="$1" state="$2" description="$3"
    payload=$(jq -n --arg s "$state" --arg d "${description:0:140}" --arg c "$STATUS_CONTEXT" \
      '{state:$s, description:$d, context:$c}')
    curl -s -X POST \
      -H "Authorization: token $GITHUB_TOKEN" \
      -H "Accept: application/vnd.github.v3+json" \
      "$API_URL/repos/$REPO_FULL_NAME/statuses/$sha" \
      -d "$payload" \
      >/dev/null
  }

  if [ "$MERGE_QUEUE_ENABLED" != "true" ]; then
    post_status "$HEAD_SHA" "success" "MergeGuard merge queue not enabled"
    exit 0
  fi

  post_status "$HEAD_SHA" "pending" "Analyzing cross-PR conflicts..."

  ANY_BLOCKED=false
  for PR_NUM in $PR_NUMBERS; do
    ANALYZE_OPTS="--repo $REPO_FULL_NAME --pr $PR_NUM --format json"
    if [ -n "${MERGEGUARD_CONFIG_PATH:-}" ]; then
      ANALYZE_OPTS="$ANALYZE_OPTS --config ${MERGEGUARD_CONFIG_PATH}"
    fi
    REPORT=$(mergeguard $GLOBAL_OPTS analyze $ANALYZE_OPTS 2>/dev/null || echo '{"conflicts":[]}')
    CONFLICT_COUNT=$(echo "$REPORT" | jq -r '.conflicts | length')
    if [ "$CONFLICT_COUNT" -gt 0 ]; then
      ANY_BLOCKED=true
    fi
  done

  if [ "$ANY_BLOCKED" = "true" ]; then
    post_status "$HEAD_SHA" "failure" "Cross-PR conflicts detected in merge group"
    exit 1
  else
    post_status "$HEAD_SHA" "success" "No blocking conflicts detected"
    exit 0
  fi
fi

# ── Standard pull_request event handling ────────────────────────────
PR_NUMBER=$(jq -r '.pull_request.number' "$GITHUB_EVENT_PATH")

# Subcommand options
ANALYZE_OPTS="--repo $REPO_FULL_NAME --pr $PR_NUMBER --format json"
if [ -n "${MERGEGUARD_CONFIG_PATH:-}" ]; then
  ANALYZE_OPTS="$ANALYZE_OPTS --config ${MERGEGUARD_CONFIG_PATH}"
fi

# Run MergeGuard and capture JSON output
REPORT=$(mergeguard $GLOBAL_OPTS analyze $ANALYZE_OPTS)

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
  mergeguard $GLOBAL_OPTS analyze \
    --repo "$REPO_FULL_NAME" \
    --pr "$PR_NUMBER" \
    --post-comment
fi

# Post merge queue status if enabled
if [ "${MERGEGUARD_MERGE_QUEUE:-false}" = "true" ]; then
  HEAD_SHA=$(jq -r '.pull_request.head.sha' "$GITHUB_EVENT_PATH")
  API_URL="https://api.github.com"
  if [ -n "${MERGEGUARD_GITHUB_URL:-}" ]; then
    API_URL="${MERGEGUARD_GITHUB_URL}/api/v3"
  fi
  STATUS_CONTEXT="mergeguard/cross-pr-analysis"

  if [ "$CONFLICT_COUNT" -gt 0 ]; then
    STATUS_STATE="failure"
    STATUS_DESC="Cross-PR conflicts detected ($CONFLICT_COUNT conflicts)"
  else
    STATUS_STATE="success"
    STATUS_DESC="No cross-PR conflicts detected"
  fi

  payload=$(jq -n --arg s "$STATUS_STATE" --arg d "${STATUS_DESC:0:140}" --arg c "$STATUS_CONTEXT" \
    '{state:$s, description:$d, context:$c}')
  curl -s -X POST \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    "$API_URL/repos/$REPO_FULL_NAME/statuses/$HEAD_SHA" \
    -d "$payload" \
    >/dev/null
fi

# Fail the check if risk exceeds threshold and fail-on-risk is set
if [ "${INPUT_FAIL_ON_RISK:-false}" = "true" ] && [ "$RISK_SCORE_INT" -ge "$THRESHOLD" ]; then
  echo "::error::MergeGuard risk score ($RISK_SCORE) exceeds threshold ($THRESHOLD)"
  exit 1
fi
