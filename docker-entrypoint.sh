#!/bin/sh
set -e

# Configure git safe directory for GitHub Actions workspace execution to ensure Git commands accept the App token identity
git config --global --add safe.directory "${GITHUB_WORKSPACE:-/github/workspace}"

# pr-number input wins; when it is empty keep any PR_NUMBER the caller set in the step env
if [ -n "${BOOMTICK_PR_NUMBER:-}" ]; then
  export PR_NUMBER="$BOOMTICK_PR_NUMBER"
fi

exec "$@"
