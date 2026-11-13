# AGENTS.md — Technical Agent Operating Protocol

This document is the primary contract and tool protocol for AI agents operating within this repository.

---

## 1. Tool Hierarchy & MCP Protocol

Agent tooling in this repository is structured into three tiers:

- **Tier 1 (MCP Protocol - Primary Interface):** When agents run in MCP-compliant hosts (e.g. Claude Code, Cursor, Antigravity CLI), connect to `boomtick-mcp` via `npx @arii/boomtick-mcp` or stdio configuration (`command: "boomtick-mcp"`). Use strongly typed MCP tools for all codebase auditing, PR analysis, and review workflows.
- **Tier 2 (`td` CLI - Secondary/Scripting Interface):** Python analytical CLI in `cli/`. Use `td` for local scripting, automated workflow execution, or as a direct fallback when MCP transport is unavailable.
- **Tier 3 (Raw Shell Commands - Fallback/Execution):** Low-level shell execution (`git`, `pnpm`, `pytest`) for file modifications, build steps, or execution environments.

### Tool Mapping Table

The MCP surface is 11 consolidated tools (schema consolidation 15 → 9/11, feat/mcp-tool-consolidation-15-to-9): `repo_context`, `repo_test`, `github_issue`, `github_create_issue`, `github_pr`, `agent_submit_pr`, `td_init`, `td_rag`, `td_validate_issue`, `td_verify_scope`, `td_audit_worktree`. The retired names (`boomtick_health`, `repo_read_agent_context`, `repo_run_tests`, `github_get_pr`, `github_issue_view`, `github_issue_update`, `github_issue_comment`, `repo_read_ci_logs`, plus the pre-existing dead `github.get_pr_diff`, `github.search_open_prs`, `github.get_merge_conflict_files`) return a "Tool not found" error.

| Task | Tier 1 (MCP) | Tier 2 (`td` CLI) | Tier 3 (Shell) |
| :--- | :--- | :--- | :--- |
| Read Agent Context Index | `repo_context` | `td context-warm` / `pnpm run agent:prime` | `cat .agent-context.json` |
| Server Health / Config | `repo_context` (`server` field) | `td doctor` | N/A |
| PR Code Review | `github_pr` (`include: ["diff", "reviews"]`) | `td ai review <PR>` | `gh pr diff <PR>` |
| Search Open PRs | `github_pr` (`search: { state: "open" }`) | `td gh search-prs` | `gh pr list` |
| View PR Details / Diff | `github_pr` (`include: ["diff"]`) | `td gh pr-diff <PR>` | `gh pr diff <PR>` |
| Fetch CI Logs / Workflow Runs | `github_pr` (`include: ["ciLogs"]` / `["workflowRuns"]`) | `td repo ci-logs <PR>` | `gh run view --log` |
| Resolve / Check Conflicts | `github_pr` (`include: ["conflicts"]`) | `td gh resolve` / `td gh merge-conflicts` | `git merge` |
| Run UX / DOM Audits | N/A (Vitest suite) | `td ux audit` | `pnpm exec vitest` |
| Dispatch Local Session | N/A (local worktree sessions) | `td agent run` | N/A |
| Run Test Suites | `repo_test` | `td test` / `td test cli` | `pnpm test` / `pytest` |
| Multi-Repo Context & Status | `repo_context` (`scope: "all"`) | `td multi-repo status` / `td multi-repo context-warm` | N/A |

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
- **`td` is the canonical CLI.** `td-cli` has been retired and will not be reintroduced. No backwards-compatibility shims, aliases, or symlinks are permitted. All agents and workflows must invoke `td`.
- **Never modify generated artifacts directly.** Trace source files and rebuild.
- **Run preflight checks (`td preflight`) before submitting PRs or finalizing changes.**
- **One-step onboarding:** Run `./setup-agent.sh` to install dependencies, build the MCP server, register host configurations via `td mcp install --execute`, and pre-warm `.agent-context.json`.

---

## 4. Commands

- `pnpm test` — run the MCP (Vitest) test suite
- `pnpm run test:python` — run the Python CLI (pytest) test suite
- `pnpm run lint` — run the lint task

## 5. Code Map

- `mcp` — MCP server source
- `cli` — Python CLI source
- `tests` — automated tests
- `docs` — project documentation

## 6. Conventions

- Use ESM `import`/`export` in TypeScript.
- Use `import` and `from ... import` in Python.
- Name TypeScript tests `*.test.ts` and Python tests `test_*.py`.
