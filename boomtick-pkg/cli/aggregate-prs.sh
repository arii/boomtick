#!/usr/bin/env bash
set -euo pipefail

# WARNING: Destructive operation - Modifies local git tracking state, pushes upstream branches, and generates remote Pull Requests.
if [ "$#" -lt 2 ]; then echo "Usage: $0 <new-branch-name> <pr1> <pr2> ..."; exit 1; fi

# Load base branch from project_config.json if possible, fallback to origin/main
CONFIG_FILE="project_config.json"
BASE_BRANCH="origin/main"
if [ -f "$CONFIG_FILE" ]; then
    # Silently attempt to load base_branch using jq if available
    if command -v jq &> /dev/null; then
        if LOADED_BRANCH=$(jq -r '.base_branch' "$CONFIG_FILE" 2>/dev/null); then
            if [ "$LOADED_BRANCH" != "null" ] && [ -n "$LOADED_BRANCH" ]; then
                BASE_BRANCH="$LOADED_BRANCH"
            fi
        else
            echo "⚠️ Warning: Failed to parse '$CONFIG_FILE'. Using default base branch '$BASE_BRANCH'." >&2
        fi
    else
        echo "⚠️ Warning: 'jq' not found. Cannot parse '$CONFIG_FILE'. Using default base branch '$BASE_BRANCH'." >&2
    fi
fi
# Extract name without remote prefix (handles origin/main, upstream/develop, etc)
BASE_BRANCH_NAME=$(echo "$BASE_BRANCH" | sed 's/.*\///')

T_BR="$1"; shift; PRs=("$@"); git checkout "$BASE_BRANCH_NAME" && git pull origin "$BASE_BRANCH_NAME" && git checkout -b "$T_BR"
P_BODY=""
for pr in "${PRs[@]}"; do
    DATA=$(gh pr view "$pr" --json headRefName,body,title --jq '.')
    REF=$(echo "$DATA" | jq -r '.headRefName') && TITLE=$(echo "$DATA" | jq -r '.title') && BODY=$(echo "$DATA" | jq -r '.body')
    gh pr checkout "$pr" 2>/dev/null && git checkout "$T_BR"
    if ! git merge "$REF" -m "Merging PR $pr: $TITLE" 2>/dev/null; then
        echo "Conflict detected in PR #$pr. Attempting automatic resolution..."
        CONFLICTED_FILES=$(git diff --name-only --diff-filter=U)
        if [ -z "$CONFLICTED_FILES" ]; then
            echo "CRITICAL: Merge failed but no conflicted files found. Aborting."
            git merge --abort
            exit 1
        fi

        if ! td-cli gh resolve; then
            echo "CRITICAL: Conflict resolution failed in PR #$pr"
            git merge --abort
            exit 1
        fi

        git add $CONFLICTED_FILES
        if ! git commit --no-edit; then
            echo "CRITICAL: Failed to commit resolved merge for PR #$pr"
            git merge --abort
            exit 1
        fi
    fi
    P_BODY="${P_BODY}Closes #$pr"$'\n\n'"### Description from PR #$pr ($TITLE):"$'\n'"$BODY"$'\n\n'"---"$'\n'
done
git push -u origin "$T_BR" && gh pr create --title "Aggregated Feature: $T_BR" --body "$P_BODY" --head "$T_BR" --base "$BASE_BRANCH_NAME"
