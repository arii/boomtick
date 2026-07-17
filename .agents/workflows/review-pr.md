# Review Pull Request

This workflow has been migrated to deterministic workflow generation.

Generate:

dev-tools/logs/workflows/workflow-plan-pr-{PR_NUMBER}.md

using:

td-cli agent plan-review \
  --pr PR_NUMBER \
  --issue ISSUE_NUMBER

Then execute:

Execute dev-tools/logs/workflows/workflow-plan-pr-{PR_NUMBER}.md
