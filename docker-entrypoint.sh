#!/bin/sh
set -e

git config --global --add safe.directory "${GITHUB_WORKSPACE:-/github/workspace}"
git config --global --add safe.directory "*"

if [ $# -gt 0 ]; then
  exec "$@"
else
  exec node /workspace/dist/runner.cjs
fi
