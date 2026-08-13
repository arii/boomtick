#!/usr/bin/env bash
# Centralized CLI path resolution for BoomTick / Tech Dancer.
# Returns the absolute path to the CLI directory.

# Find repo root if not provided
REPO_ROOT="${REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"

if [ -d "${REPO_ROOT}/cli" ]; then
    printf "%s\n" "${REPO_ROOT}/cli"
elif [ -d "${REPO_ROOT}/boomtick-pkg/cli" ]; then
    printf "%s\n" "${REPO_ROOT}/boomtick-pkg/cli"
elif [ -d "${REPO_ROOT}/boomtick/cli" ]; then
    printf "%s\n" "${REPO_ROOT}/boomtick/cli"
else
    # Fallback to REPO_ROOT if neither is found (e.g. inside the cli dir already)
    # But only if we can find a pyproject.toml here.
    if [ -f "pyproject.toml" ]; then
        printf "%s\n" "$(pwd -P)"
    else
        # Last resort: error out
        echo "Error: Could not resolve CLI_ROOT" >&2
        exit 1
    fi
fi
