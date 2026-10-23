#!/usr/bin/env bash
set -u

cd "$(dirname "$0")/.."
source ./.agent-env.sh 2>/dev/null || true
export ALLOW_HELP=1

REPORT="cli/logs/workflow-verification.md"
mkdir -p cli/logs

echo "# Workflow Verification" > "$REPORT"
echo >> "$REPORT"
echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$REPORT"
echo >> "$REPORT"

echo "| Workflow | Command | Result |" >> "$REPORT"
echo "|---|---|---|" >> "$REPORT"

ok() { echo "✅ $*"; }
warn() { echo "⚠️  $*"; }

repair_origin() {
  if git remote get-url origin >/dev/null 2>&1; then
    return 0
  fi
  local slug="${GITHUB_REPOSITORY:-${REPO_SLUG:-}}"
  if [ -n "$slug" ]; then
    git remote add origin "https://github.com/${slug}.git" >/dev/null 2>&1 || true
  fi
}

run_check() {
  local workflow="$1"; shift
  local cmd="$*"
  if eval "$cmd" >/dev/null 2>&1; then
    ok "$cmd"
    echo "| ${workflow} | \`${cmd}\` | ✅ pass |" >> "$REPORT"
  else
    warn "$cmd"
    echo "| ${workflow} | \`${cmd}\` | ⚠️ warn |" >> "$REPORT"
  fi
}

echo "== Verifying .agents/workflows =="
repair_origin

run_check "shared" "python3 --version"
run_check "shared" "pnpm --version"
run_check "shared" "PYTHONPATH=\"cli:cli/dev_tools\" td gh --help"
run_check "shared" "PYTHONPATH=\"cli:cli/dev_tools\" td agent --help"

run_check "ai-slop-audit.md" "python3 .agents/scripts/audit-ai-slop.py"

run_check "dev-tools-cli-guide.md" "PYTHONPATH=\"cli:cli/dev_tools\" td gh pre-submit --help"
run_check "dev-tools-cli-guide.md" "PYTHONPATH=\"cli:cli/dev_tools\" td gh audit-pr --help"
run_check "dev-tools-cli-guide.md" "PYTHONPATH=\"cli:cli/dev_tools\" td gh validate-issue --help"

run_check "review-pr.md" "PYTHONPATH=\"cli:cli/dev_tools\" td agent plan-review --help"

run_check "review-ux.md" "npx playwright --version"
run_check "review-ux.md" "node scripts/detect-antipatterns.mjs --help"

echo "== Done =="
echo "Report: $REPORT"
