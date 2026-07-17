#!/usr/bin/env bash
# usage: ./download_run.sh <RUN_ID>

RUN_ID=$1
REPO=${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "arii/boomtick")}
DEST_DIR=${DEST_DIR:-"./runs/run-$RUN_ID"}

if [ -z "$RUN_ID" ]; then
  echo "❌ Please provide a workflow Run ID."
  echo "Usage: ./download_run.sh 29507773139"
  exit 1
fi

if ! [[ "$RUN_ID" =~ ^[0-9]+$ ]]; then
  echo "❌ Run ID must be numeric."
  exit 1
fi

mkdir -p "$DEST_DIR"

echo "Checking if 'deployment-review' exists on Run ID: $RUN_ID in repo $REPO..."

# 1. Verify if the artifact is available for this run
ARTIFACT_EXISTS=$(gh api "repos/$REPO/actions/runs/$RUN_ID/artifacts" \
  --jq '.artifacts[] | select(.name == "deployment-review") | .name' 2>/dev/null)

if [ "$ARTIFACT_EXISTS" = "deployment-review" ]; then
  echo "✅ Artifact found. Downloading to $DEST_DIR..."

  # 2. Download and unzip the target artifact
  gh run download "$RUN_ID" -n "deployment-review" -D "$DEST_DIR" --repo "$REPO"

  echo "🎉 Download complete. Files saved in $DEST_DIR:"
  ls -la "$DEST_DIR"
else
  echo "⚠️  No 'deployment-review' artifact associated with Run ID $RUN_ID."
  # Clean up directory if empty
  rmdir "$DEST_DIR" 2>/dev/null
fi
