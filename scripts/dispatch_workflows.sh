#!/usr/bin/env bash
set -euo pipefail

# Script to dispatch boomtick workflows on a specific branch

BRANCH="${1:-}"
if [ -z "$BRANCH" ]; then
  echo "Usage: $0 <branch-name> [issue-pr-number]"
  exit 1
fi

ISSUE_NUM="${2:-308}"
REPO="arii/boomtick"

echo "Dispatching workflows on branch: $BRANCH (Repo: $REPO) using Issue/PR #: $ISSUE_NUM..."

echo "1. Dispatching CI Repair (ci-repair.yml)..."
gh workflow run ci-repair.yml -R "$REPO" --ref "$BRANCH" -f issue_number="$ISSUE_NUM" -f comment_body="manual run"

echo "2. Dispatching Issue Operations (issue-operations.yml) with ai-review..."
gh workflow run issue-operations.yml -R "$REPO" --ref "$BRANCH" -f action="ai-review" -f issue_number="$ISSUE_NUM" -f comment_body="manual run"

echo "Dispatched successfully! To list runs, execute:"
echo "gh run list -R $REPO --branch $BRANCH"
