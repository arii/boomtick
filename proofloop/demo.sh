#!/usr/bin/env bash
# One-command demo prep: validate data, run the full loop (including the bad-mutation rollback),
# then serve the backend + dashboard. Uses live Senso/OpenRouter if their keys are set (env or proofloop/.env).
set -euo pipefail
cd "$(dirname "$0")/harness"
PY="${PYTHON:-python3}"
if [ -x ../.venv/bin/python ]; then PY=../.venv/bin/python; fi
$PY health.py || true
$PY validate.py
$PY replay_loop.py --reset --bad-demo
echo
echo "Dashboard: http://127.0.0.1:8787/   (extension chip reads /augment from the same server)"
exec $PY server.py 8787
