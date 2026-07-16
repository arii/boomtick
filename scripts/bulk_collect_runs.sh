#!/usr/bin/env bash

WORKFLOW_NAME=${WORKFLOW_NAME:-"Deployment Impact Analysis"}
REPO=${REPO:-"arii/boomtick"}
LIMIT_RUNS=${LIMIT_RUNS:-50}
BASE_DIR="./collected-logs"

echo "🔍 Fetching the last $LIMIT_RUNS runs of '$WORKFLOW_NAME' from '$REPO'..."

# Get a list of the recent run IDs
RUN_IDS=$(gh run list \
  --workflow="$WORKFLOW_NAME" \
  --limit "$LIMIT_RUNS" \
  --json databaseId \
  --jq '.[].databaseId' \
  --repo "$REPO")

if [ -z "$RUN_IDS" ]; then
  echo "❌ No runs found for workflow '$WORKFLOW_NAME' in '$REPO'."
  exit 1
fi

process_run() {
  local RUN_ID=$1
  echo "----------------------------------------"
  echo "Processing Run ID: $RUN_ID"

  # Check if a 'deployment-review' artifact exists for this Run ID
  local HAS_ARTIFACT=$(gh api "repos/$REPO/actions/runs/$RUN_ID/artifacts" \
    --jq '.artifacts[] | select(.name == "deployment-review") | .id' 2>/dev/null)

  if [ -n "$HAS_ARTIFACT" ]; then
    local RUN_DIR="$BASE_DIR/run-$RUN_ID"

    # Avoid re-downloading if we already pulled it locally
    if [ -d "$RUN_DIR" ] && [ "$(ls -A "$RUN_DIR" 2>/dev/null)" ]; then
      echo "⏭️  Run $RUN_ID already downloaded. Skipping."
      return 0
    fi

    mkdir -p "$RUN_DIR"
    echo "📥 Downloading 'deployment-review' artifact for Run $RUN_ID..."

    # Download the zipped files directly into the run directory
    if gh run download "$RUN_ID" -n "deployment-review" -D "$RUN_DIR" --repo "$REPO"; then
      echo "✅ Successfully saved to $RUN_DIR"
    else
      echo "❌ Failed to download artifact for Run $RUN_ID."
      rm -rf "$RUN_DIR"
    fi
  else
    echo "ℹ️  Run $RUN_ID has no 'deployment-review' artifact. Skipping."
  fi
}

export -f process_run
export REPO
export BASE_DIR

echo "$RUN_IDS" | xargs -P 5 -I {} bash -c 'process_run "$@"' _ {}

echo "========================================"
echo "🎉 Bulk collection complete. Logs are grouped in '$BASE_DIR/'."
