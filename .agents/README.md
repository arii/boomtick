# .agents/

This directory contains the agent operating contract, tooling protocols,
workflows, and supporting scripts for automated operations in this repository.

## Installable skills

- [`actions-health-check`](skills/actions-health-check/SKILL.md): sample recent GitHub Actions outcomes and elapsed times without rerunning CI.
- [`add-boomtick-review`](skills/add-boomtick-review/SKILL.md): add opt-in BoomTick PR review to a downstream repo.
- [`agent-ledger-intake`](skills/agent-ledger-intake/SKILL.md): file a task for the S5 queue as one Agent Ledger Form row.

Install an individual skill into your local agent. For example, use the
[Skills CLI](https://github.com/vercel-labs/skills) for a personal Codex install:

```sh
npx skills add arii/boomtick --skill actions-health-check --agent codex -g
```

Replace `codex` with `claude-code`, `cursor`, or `devin`. For a manual
project install, copy the whole skill directory into your agent's skill path:

| Agent | Project skill path |
| --- | --- |
| [Claude Code](https://code.claude.com/docs/en/skills) | `.claude/skills/` |
| [Codex](https://developers.openai.com/codex/skills/) | `.agents/skills/` |
| [Cursor](https://cursor.com/docs/context/skills) | `.cursor/skills/` |
| [Devin CLI](https://docs.devin.ai/cli/extensibility/skills/overview) | `.devin/skills/` |

For a Devin cloud session, install an individual skill via **Customize → Skills** using its
Markdown, or place it in the target checkout's `.devin/skills/` directory.
Install or copy the skills you need; there's no requirement to run BoomTick's setup first.

---

## Core Standards

- **`AGENTS.md`** — Primary Tooling and MCP Protocol. Defines the three-tier
  tool hierarchy (MCP → `td` → bash), the full tool mapping table, and
  enforcement rules. **Read this before any GitHub or repository operation.**
- **`AGENT_CONTRACT.md`** — Invariant rules for agent behavior. Always wins
  over other instruction layers.
- **`INSTRUCTION_LAYERS.md`** — Reference for which file governs which concern
  and how conflicts are resolved.

---

## Workflows

Located in `.agents/workflows/`:

- **`ci-remediation.md`** — Protocol for diagnosing and dispatching CI repair
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
- `cli_schema` — full `td` command/flag reference
- `package_json` — dependency and script metadata

It is rebuilt by `pnpm run agent:prime` (manual). The `post-merge` hook in
`scripts/hooks/` runs `td init` after a pull or merge; nothing runs on branch
switch.

If the index is stale, run `pnpm run agent:prime` before any agent operation.
