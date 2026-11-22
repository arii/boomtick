#!/usr/bin/env bash
# Clean-install smoke test for the td CLI (#1368).
# Installs cli/ into a fresh venv with no repo-root PYTHONPATH, then runs
# `td --help` and two read-only commands with no GitHub credentials.
# The CPU-only torch index avoids downloading CUDA wheels pulled in by
# sentence-transformers.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv="${1:-$(mktemp -d)/venv}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

python3 -m venv "$venv"
"$venv/bin/pip" install --quiet \
  --extra-index-url https://download.pytorch.org/whl/cpu "$repo_root/cli"

# Run from outside the checkout with a scrubbed environment.
cat > "$work/spec.md" <<'SPEC'
# Smoke
## Problem Statement
Smoke spec.
SPEC
cd "$work"
run_td() {
  env -i PATH="/usr/bin:/bin" HOME="$work" "$venv/bin/td" "$@"
}
run_td --help > /dev/null
run_td --json schema | "$venv/bin/python" -c 'import json,sys; assert json.load(sys.stdin)["status"] == "success"'
# validate-issue exits 1 for an invalid spec; any other failure is an error.
rc=0
out="$(run_td --json validate-issue --file spec.md --repo-root "$work")" || rc=$?
[ "$rc" -eq 1 ] || { echo "validate-issue exited $rc, expected 1" >&2; exit 1; }
echo "$out" | "$venv/bin/python" -c 'import json,sys; assert json.load(sys.stdin)["valid"] is False'
echo "td clean-install smoke passed"
