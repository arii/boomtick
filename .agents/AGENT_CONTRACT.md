# Agent Contract

This document defines the invariant rules for all agent behavior in this
repository. These rules **always win** over any other instruction layer.

Read the matching workflow before starting these task types:
- PR review → `.agents/workflows/review-pr.md`
- UX audit → `.agents/workflows/review-ux.md`
- CI repair → `.agents/workflows/fix-ci.md`

---

## What You Will Always Do

- Read all referenced files before taking any action.
- **Prioritize Index & Schema**: Always consult `.agent-context.json` for
  repository state and `dev-tools/cli-schema.json` for CLI authority before
  taking action. Both are available via `repo.read_agent_context` (Tier 1).
- **Prioritize MCP Tools**: Consult the tool hierarchy in `.agents/AGENTS.md`
  before executing any repository or GitHub operation. `boomtick-mcp` is the
  required first call — not an optional convenience.
- Update the workflow state machine header before proceeding past each step.
- Produce output only to the specified output files.
- Never write to `pr-context-*.md` files (read-only by convention).

---

## What You Will Never Do

- Call `td_cli.py` directly when an MCP tool covers the same operation.
- Call raw bash (`gh`, `git`) when a Tier 1 or Tier 2 tool covers the operation.
- Use `--help` or `-h` to discover CLI flags — read `cli_schema` from
  `.agent-context.json` instead.
- Guess flags not listed in `dev-tools/cli-schema.json`.
- Chain subcommands in a single shell call.
- Use interactive menus.
- Change the Node.js or pnpm runtime versions without explicit instruction.
- Delete `pnpm-lock.yaml`.
- Add `use-node-version` to `.npmrc`.

---

## Validation Failure Protocol

If environment validation fails (runtime mismatch, missing token, stale index):

1. Stop immediately.
2. Report the exact mismatch.
3. Do not attempt to bypass or self-correct the runtime contract.
4. If `.agent-context.json` is stale, run `pnpm run agent:prime` and re-read
   before proceeding.
