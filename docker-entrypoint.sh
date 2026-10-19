#!/bin/sh
set -e

# Configure git safe directory for GitHub Actions workspace execution to ensure Git commands accept the App token identity
git config --global --add safe.directory "${GITHUB_WORKSPACE:-/github/workspace}"

exec "$@"
