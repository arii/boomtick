# AGENTS.md — Technical Agent Operating Protocol

This document is the primary contract and tool protocol for AI agents operating within this repository.

---

## 1. Tool Hierarchy & MCP Protocol

Agent tooling in this repository is structured into three tiers:

- **Tier 1 (MCP Protocol - Primary Interface):** When agents run in MCP-compliant hosts (e.g. Claude Code, Cursor, Antigravity CLI), connect to `boomtick-mcp` via `npx @arii/boomtick-mcp` or stdio configuration (`command: "boomtick-mcp"`). Use strongly typed MCP tools for all codebase auditing, PR analysis, and review workflows.
- **Tier 2 (`td` CLI - Secondary/Scripting Interface):** Python analytical CLI in `cli/`. Use `td` for local scripting, automated workflow execution, or as a direct fallback when MCP transport is unavailable.
- **Tier 3 (Raw Shell Commands - Fallback/Execution):** Low-level shell execution (`git`, `pnpm`, `pytest`) for file modifications, build steps, or execution environments.

### Tool Mapping Table

| Task | Tier 1 (MCP) | Tier 2 (`td` CLI) | Tier 3 (Shell) |
| :--- | :--- | :--- | :--- |
| Read Agent Context Index | `repo.read_agent_context` | `td context-warm` | `cat .agent-context.json` |
| PR Code Review | `ai.review_pr` | `td ai review <PR>` | `gh pr diff <PR>` |
| Search Open PRs | `github.search_prs` | `td gh search-prs` | `gh pr list` |
| View PR Details / Diff | `github.get_pr_diff` | `td gh pr-diff <PR>` | `gh pr diff <PR>` |
| Fetch CI Logs | `repo.get_ci_logs` | `td repo ci-logs <PR>` | `gh run view --log` |
| Resolve Merge Conflicts | `github.resolve_conflicts` | `td gh resolve` | `git merge` |
| Run UX / DOM Audits | `ux.run_audit` | `td ux audit` | `pnpm exec vitest` |
| Dispatch Jules Session | `jules.dispatch` | `td agent dispatch` | N/A |
| Multi-Repo Context & Status | `repo.read_agent_context(all=true)` | `td multi-repo status` | N/A |
| Sequential Multi-Repo Exec | `repo.multi_exec` | `td multi-repo exec "<cmd>"` | N/A |
| Multi-Repo Context Warming | `repo.read_agent_context` | `td multi-repo context-warm` | N/A |

---

## 2. MCP Configuration & Registration Instructions

### Automated Configuration Helper

Agents or developers can run the automated configuration helper via `td`:

```bash
td mcp install
# or
td mcp setup
```

This command automatically detects installed agent hosts (Antigravity CLI, Claude Code, Cursor, VS Code / Codex) and registers `boomtick-mcp` into their respective configuration files.

### Configuration Snippets by Host

#### Google Antigravity CLI
Config path: `~/.gemini/antigravity-cli/settings.json` or `.gemini/settings.json`

```json
{
  "mcpServers": {
    "boomtick": {
      "command": "boomtick-mcp"
    }
  }
}
```

#### Claude Code
Config path: `~/.claude.json` or `.claude/mcp.json`

```json
{
  "mcpServers": {
    "boomtick": {
      "command": "npx",
      "args": ["-y", "@arii/boomtick-mcp"]
    }
  }
}
```

#### Cursor
Config path: `~/.cursor/mcp.json` or `.cursor/mcp.json`

```json
{
  "mcpServers": {
    "boomtick": {
      "command": "boomtick-mcp"
    }
  }
}
```

---

## 3. Core Standards & Invariants

- **Always prefer Tier 1 MCP tools when connected.**
- **Never modify generated artifacts directly.** Trace source files and rebuild.
- **Run preflight checks (`td preflight`) before submitting PRs or finalizing changes.**
