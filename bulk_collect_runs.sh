#!/usr/bin/env bash

WORKFLOW_NAME="Deployment Impact Analysis"
LIMIT_RUNS=50
BASE_DIR="./collected-logs"

echo "🔍 Fetching the last $LIMIT_RUNS runs of '$WORKFLOW_NAME'..."

# Get a list of the recent run IDs
RUN_IDS=$(gh run list \
  --workflow="$WORKFLOW_NAME" \
  --limit "$LIMIT_RUNS" \
  --json databaseId \
  --jq '.[].databaseId' \
  --repo arii/boomtick 2>/dev/null)

if [ -z "$RUN_IDS" ]; then
  echo "❌ No runs found for workflow '$WORKFLOW_NAME'."
  exit 1
fi

for RUN_ID in $RUN_IDS; do
  echo "----------------------------------------"
  echo "Processing Run ID: $RUN_ID"

  # Check if a 'deployment-review' artifact exists for this Run ID
  HAS_ARTIFACT=$(gh api "repos/arii/boomtick/actions/runs/$RUN_ID/artifacts" \
    --jq '.artifacts[] | select(.name == "deployment-review") | .id' 2>/dev/null)

  if [ -n "$HAS_ARTIFACT" ]; then
    RUN_DIR="$BASE_DIR/run-$RUN_ID"

    # Avoid re-downloading if we already pulled it locally
    if [ -d "$RUN_DIR" ] && [ "$(ls -A "$RUN_DIR" 2>/dev/null)" ]; then
      echo "⏭️  Run $RUN_ID already downloaded. Skipping."
      continue
    fi

    mkdir -p "$RUN_DIR"
    echo "📥 Downloading 'deployment-review' artifact for Run $RUN_ID..."

    # Download the zipped files directly into the run directory
    gh run download "$RUN_ID" -n "deployment-review" -D "$RUN_DIR" --repo arii/boomtick 2>/dev/null

    if [ $? -eq 0 ]; then
      echo "✅ Successfully saved to $RUN_DIR"
    else
      echo "❌ Failed to download artifact for Run $RUN_ID."
      rm -rf "$RUN_DIR"
    fi
  else
    echo "ℹ️  Run $RUN_ID has no 'deployment-review' artifact. Skipping."
  fi
done

echo "========================================"
echo "🎉 Bulk collection complete. Logs are grouped in '$BASE_DIR/'."
