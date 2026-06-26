# .agents/

This directory contains the agent operating contract, tooling protocols,
workflows, and supporting scripts for automated operations in this repository.

---

## Core Standards

- **`AGENTS.md`** — Primary Tooling and MCP Protocol. Defines the three-tier
  tool hierarchy (MCP → `td_cli.py` → bash), the full tool mapping table, and
  enforcement rules. **Read this before any GitHub or repository operation.**
- **`AGENT_CONTRACT.md`** — Invariant rules for agent behavior. Always wins
  over other instruction layers.
- **`INSTRUCTION_LAYERS.md`** — Reference for which file governs which concern
  and how conflicts are resolved.

---

## Workflows

Located in `.agents/workflows/`:

- **`fix-ci.md`** — Protocol for diagnosing and dispatching CI repair via Jules
- **`review-pr.md`** — PR review workflow
- **`review-ux.md`** — UX audit workflow
- **`ai-slop-audit-[DATE].md`** — Auto-generated audit results (latest run)

---

## Scripts

Located in `.agents/scripts/`:

Supporting scripts for workflow automation. These are called by workflows or
MCP tools — do not invoke directly unless a workflow explicitly instructs it.

---

## Context Index

`.agent-context.json` (repository root) is the pre-built index consumed by
`boomtick-mcp` on every tool call. It contains:

- `file_tree` — repository structure snapshot
- `cli_schema` — full `td_cli.py` command/flag reference
- `package_json` — dependency and script metadata

It is rebuilt automatically by:
- `pnpm run agent:prime` (manual)
- `.githooks/post-checkout` and `.githooks/post-merge` (automatic on branch
  switch or pull)

If the index is stale, run `pnpm run agent:prime` before any agent operation.
