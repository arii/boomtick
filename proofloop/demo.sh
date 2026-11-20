#!/usr/bin/env bash
# Offline demo only. --serve explicitly starts the local read-only backend.
set -euo pipefail
if [ $# -gt 1 ] || { [ $# -eq 1 ] && [ "$1" != "--serve" ]; }; then
  echo "Usage: $0 [--serve] (always offline; does not activate sponsors)" >&2
  exit 2
fi
SERVE="${1:-}"
cd "$(dirname "$0")/harness"
PY="${PYTHON:-python3}"
if [ -x ../.venv/bin/python ]; then PY=../.venv/bin/python; fi
export PROOFLOOP_FORCE_STUB=1
export PROOFLOOP_STATE="${PROOFLOOP_STATE:-../state/offline-demo}"
"$PY" health.py
"$PY" validate.py
"$PY" replay_loop.py --reset --bad-demo
if [ "$SERVE" = "--serve" ]; then
  echo "Offline dashboard: http://127.0.0.1:8787/"
  exec "$PY" server.py 8787
fi
