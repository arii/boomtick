# Instruction Layers

| File | Use For | Never Use For |
| -------------------------------- | ------------------------------- | ----------------------- |
| `.agents/AGENT_CONTRACT.md` | Invariant rules (always wins) | Specify CLI flags |
| `dev-tools/cli-schema.json` | Canonical CLI authority | Define UI style rules |
| `AGENTS.md` | TSX, PR lifecycle, runtime rules | Duplicate CLI schema |
| `.agents/AGENTS.md` | MCP tool hierarchy, tool mapping | Redefine contract rules |
| `.agents/workflows/` | Task-specific protocols | Redefine core rules |
| `audit.config.yaml` | Define what is bad | Suggest fixes or report |
| `docs/agent/issue-audit-rules.md` | Issue audit rules | Implementation details |

## Resolution Order

When two layers conflict, the higher row wins. `AGENT_CONTRACT.md` always
takes precedence. `cli-schema.json` always wins over any example in `AGENTS.md`
or a workflow file.

## Key Relationships

- `.agent-context.json` embeds `cli_schema` and `file_tree` — a single read
  covers both `cli-schema.json` and repository structure. Use
  `repo.read_agent_context` (Tier 1 MCP) to get it.
- `.agents/AGENTS.md` defines the MCP → `td_cli.py` → bash escalation path
  for every task category. Consult it before any GitHub or repo operation.
- `CODEX.md` has been removed — its runtime contract is now in `AGENTS.md`
  section 22 and enforced by `dev-tools/setup-agent.sh`.
