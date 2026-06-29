# Workflow Verification

Generated: 2026-06-29T20:57:02Z

| Workflow | Command | Result |
|---|---|---|
| shared | `python3 --version` | ✅ pass |
| shared | `pnpm --version` | ✅ pass |
| shared | `PYTHONPATH="boomtick-pkg/cli:boomtick-pkg/cli/dev_tools" python3 boomtick-pkg/cli/dev_tools/td_cli.py gh --help` | ✅ pass |
| shared | `PYTHONPATH="boomtick-pkg/cli:boomtick-pkg/cli/dev_tools" python3 boomtick-pkg/cli/dev_tools/td_cli.py jules --help` | ✅ pass |
| ai-slop-audit.md | `python3 .agents/scripts/audit-ai-slop.py` | ✅ pass |
| dev-tools-cli-guide.md | `PYTHONPATH="boomtick-pkg/cli:boomtick-pkg/cli/dev_tools" python3 boomtick-pkg/cli/dev_tools/td_cli.py gh pre-submit --help` | ✅ pass |
| dev-tools-cli-guide.md | `PYTHONPATH="boomtick-pkg/cli:boomtick-pkg/cli/dev_tools" python3 boomtick-pkg/cli/dev_tools/td_cli.py gh audit-pr --help` | ✅ pass |
| dev-tools-cli-guide.md | `PYTHONPATH="boomtick-pkg/cli:boomtick-pkg/cli/dev_tools" python3 boomtick-pkg/cli/dev_tools/td_cli.py gh validate-issue --help` | ✅ pass |
| review-pr.md | `PYTHONPATH="boomtick-pkg/cli:boomtick-pkg/cli/dev_tools" python3 boomtick-pkg/cli/dev_tools/td_cli.py gh audit-pr 2821 --fetch` | ⚠️ warn |
| review-ux.md | `npx playwright --version` | ✅ pass |
| review-ux.md | `node scripts/detect-antipatterns.mjs --help` | ✅ pass |
