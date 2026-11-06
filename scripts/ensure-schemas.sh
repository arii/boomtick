#!/usr/bin/env bash
# Regenerate the gitignored CLI schema files when they are missing.
# Never fails: every caller treats this as best-effort (readers
# tolerate absent files, and verify:schemas regenerates anyway).
# - cli-schema.json (pydantic models): via `td schema --generate`
#   when td is on PATH, else `python3 -m dev_tools.schema_gen`.
# - cli-commands-schema.json (command tree): regenerated as a side
#   effect of `td context-warm` (build-repo-context.py); not built
#   here because a full context build is too heavy for a hook.
set -u
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)" || exit 0

# Sync canonical visual_guidelines.json from cli resources into lib/resources (#1143)
if [ -f "cli/dev_tools/resources/visual_guidelines.json" ]; then
  cp cli/dev_tools/resources/visual_guidelines.json lib/resources/visual_guidelines.json
fi

MODELS_SCHEMA="cli/dev_tools/cli-schema.json"
if [ -f "$MODELS_SCHEMA" ]; then
  exit 0
fi

# Repo-local generation first: an installed `td` may resolve
# dev_tools to its own venv copy instead of this checkout.
if [ -f "cli/dev_tools/schema_gen.py" ]; then
  PYTHONPATH="cli${PYTHONPATH:+:$PYTHONPATH}" python3 -m dev_tools.schema_gen >/dev/null 2>&1 && exit 0
  echo "[ensure-schemas] schema_gen failed (deps installed?); continuing without $MODELS_SCHEMA" >&2
  exit 0
fi

if command -v td >/dev/null 2>&1; then
  td schema --generate >/dev/null 2>&1 && exit 0
  echo "[ensure-schemas] td schema --generate failed; continuing without $MODELS_SCHEMA" >&2
  exit 0
fi

echo "[ensure-schemas] no generator available; continuing without $MODELS_SCHEMA" >&2
exit 0
