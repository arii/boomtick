#!/usr/bin/env bash
set -Eeuo pipefail

echo "=== Bootstrapping Agent Workspace ==="

# 1. Dependency Installation
# Strict deterministic installation without fallbacks
pnpm install --frozen-lockfile

# 2. Python tooling installation
pip3 install --break-system-packages -e ./dev-tools

# 3. Environment Check
node --version
pnpm --version
python3 --version
echo "=== Bootstrapping Complete ==="
