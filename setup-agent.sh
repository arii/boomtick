#!/usr/bin/env bash
set -Eeuo pipefail

echo "=== Bootstrapping Agent Workspace ==="

# 1. Parity Check
if [ -f /.dockerenv ] || grep -q 'docker' /proc/1/cgroup 2>/dev/null; then
  echo "✔ Running inside workspace Docker container."
else
  echo "⚠ Running outside the Docker container. Falling back to local bootstrapping..."
  corepack enable
  corepack prepare pnpm@10.28.2 --activate
fi

# 2. Dependency Installation
pnpm install --frozen-lockfile

# 3. Environment Check
node --version
pnpm --version
python3 --version
echo "=== Bootstrapping Complete ==="
