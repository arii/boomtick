#!/usr/bin/env bash
# Install tracked hooks from scripts/hooks/ into .git/hooks.
# Usage: bash scripts/setup-hooks.sh [--copy]
# Default mode symlinks so edits to the tracked copies take effect
# immediately; --copy snapshots them instead (e.g. for tooling that
# dislikes symlinks).
set -u
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)" || exit 1

HOOK_SRC="scripts/hooks"
HOOK_DST=".git/hooks"
mode="link"
[ "${1:-}" = "--copy" ] && mode="copy"

if [ ! -d "$HOOK_SRC" ]; then
  echo "setup-hooks: $HOOK_SRC not found" >&2
  exit 1
fi
if [ ! -d "$HOOK_DST" ]; then
  echo "setup-hooks: $HOOK_DST not found (not a git checkout?)" >&2
  exit 1
fi

for src in "$HOOK_SRC"/*; do
  name="$(basename "$src")"
  dst="$HOOK_DST/$name"
  # Never touch the .sample templates git ships.
  case "$name" in *.sample) continue;; esac
  rm -f "$dst"
  if [ "$mode" = "copy" ]; then
    cp "$src" "$dst"
  else
    ln -s "../../$src" "$dst"
  fi
  chmod +x "$dst"
  echo "setup-hooks: installed $name ($mode)"
done
