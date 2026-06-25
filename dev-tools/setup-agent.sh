#!/usr/bin/env bash
set -Eeuo pipefail

corepack enable
corepack prepare pnpm@10.28.2 --activate

pip3 install --break-system-packages -e ./dev-tools
pnpm install --frozen-lockfile
echo "Environment bootstrapping succeeded."
