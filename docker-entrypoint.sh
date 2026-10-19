#!/bin/sh
set -e

# Configure git safe directory for GitHub Actions workspace execution
git config --global --add safe.directory "${GITHUB_WORKSPACE:-/github/workspace}"
git config --global --add safe.directory '/workspace'
git config --global --add safe.directory '*'

exec "$@"
