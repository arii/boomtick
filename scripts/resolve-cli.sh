#!/usr/bin/env bash
set -euo pipefail

# Dynamically resolve workspace root and node_modules bin directory
WORKSPACE_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
LOCAL_BIN="$(cd "${WORKSPACE_ROOT}" && pnpm bin 2>/dev/null || echo "${WORKSPACE_ROOT}/node_modules/.bin")"

# Prepend resolved bin path to PATH
export PATH="${LOCAL_BIN}:${PATH}"

if [ $# -gt 0 ]; then
    # Execute command using dynamic PATH resolution
    exec "$@"
else
    # Fallback/Original behavior: Centralized CLI path resolution for BoomTick / Tech Dancer.
    # Returns the absolute path to the CLI directory.
    REPO_ROOT="${WORKSPACE_ROOT}"
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
fi
