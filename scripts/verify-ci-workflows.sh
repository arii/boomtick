#!/usr/bin/env bash
set -euo pipefail

# Get directory of the script and go to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."

echo "==========================================="
echo "Running CI Workflows Static Audit..."
echo "==========================================="

python3 scripts/verify-ci-workflows.py
