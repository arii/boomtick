# Tooling and MCP Protocol

This protocol defines the tool selection hierarchy to ensure fast, reliable, and
context-aware operations. Agents **must** prioritize specialized tools over
general-purpose shell commands.

---

## 🧠 Intelligence First: Index and Schema

Before executing **any** command, agents MUST:

1. **Consult `.agent-context.json`** — ground truth for repository structure,
   `file_tree`, `cli_schema`, current feature flags, and metadata. This file is
   built by `boomtick-pkg/scripts/build-repo-context.py` and kept fresh by the git hooks in
   `.githooks/`.
2. **Consult `boomtick-pkg/cli/dev_tools/cli-schema.json`** — canonical authority for local CLI
   commands. Never guess flags. Never run `--help`. The schema is also embedded
   in `.agent-context.json` under the `cli_schema` key, so a single read of that
   file covers both.

---

## ⚠️ Enforcement: MCP is Not Optional

Tier 1 MCP tools are the **required first call** — not a preference.

Every `boomtick-mcp` tool automatically:
1. Reads `.agent-context.json` to inject `file_tree` and `cli_schema` into context
2. Calls the appropriate `td_cli.py` subcommand internally
3. Returns structured output with repo context already attached

Calling `td_cli.py` directly (Tier 2) skips step 1.
Calling raw bash (Tier 3) skips steps 1 and 2.

**Violation pattern to avoid:**

```bash
# ❌ Wrong — bypasses MCP, no context injection, no index hydration
python3 boomtick-pkg/cli/dev_tools/td_cli.py gh pr-diff 2280

# ✅ Correct — MCP hydrates .agent-context.json, calls td_cli.py internally
github.get_pr_diff(pr_number=2280)
```

Only escalate to a lower tier if the MCP tool is **genuinely unavailable**. If an MCP tool or dev-tool command fails or requires fallback to a lower tier, you MUST document the issue in the CLI Failure Ledger (within `progress_and_next_steps.md`) rather than silently bypassing it.

---

## 🧬 Hierarchy of Tooling

| Tier | Tool | When to Use |
| :--- | :--- | :--- |
| **Tier 1** | `boomtick-mcp` tools | Always — primary entry point for all repo and GitHub operations |
| **Tier 2** | `boomtick-pkg/cli/dev_tools/td_cli.py` | Only when a Tier 1 tool is unavailable or the CLI provides logic not yet exposed via MCP |
| **Tier 3** | Raw bash / `gh` CLI | Last resort — only when no Tier 1 or Tier 2 tool exists for the task |

---

## 🗺️ Tool Mapping Table

| Category | Task | Tier 1: MCP (required first) | Tier 2: `td_cli.py` (fallback) | Tier 3: Bash (last resort) |
| :--- | :--- | :--- | :--- | :--- |
| **GitHub** | Search PRs | `github.search_open_prs` | `td_cli.py gh search-prs` | `gh pr list` |
| **GitHub** | Get PR Diff | `github.get_pr_diff` | `td_cli.py gh pr-diff <PR>` | `gh pr diff <PR>` |
| **GitHub** | Check Conflicts (global) | `github.get_merge_conflict_files` | `td_cli.py gh conflicts` | - |
| **GitHub** | Detect Conflicts (single PR) | `github.get_merge_conflict_files` | `td_cli.py gh detect-conflicts --pr <PR>` | `git merge-tree` |
| **GitHub** | Merge Conflicts (PR vs base) | `github.get_merge_conflict_files` | `td_cli.py gh merge-conflicts <PR>` | - |
| **GitHub** | Resolve Conflicts | `github.create_repair_branch` | `td_cli.py gh resolve-conflicts --pr <PR>` | - |
| **GitHub** | Comment on PR | `github.comment_triage_summary` | `td_cli.py gh audit-pr <PR> --submit` | `gh pr comment` |
| **GitHub** | Status Board | `github.get_status_board` | `td_cli.py gh status-board` | - |
| **GitHub** | PR Overlaps | `github.analyze_overlaps` | `td_cli.py gh overlaps` | - |
| **GitHub** | Audit PR | `github.audit_pr` | `td_cli.py gh audit-pr <PR> --fetch --audit` | - |
| **GitHub** | Manage Reviews | `github.manage_reviews` | `td_cli.py gh manage-reviews` | - |
| **GitHub** | Validate Issue | `github.validate_issue` | `td_cli.py gh validate-issue` | - |
| **GitHub** | Create Issue | `github.create_issue` | `td_cli.py gh create-issue` | `gh issue create` |
| **GitHub** | Pre-submit Gate | `github.pre_submit` | `td_cli.py gh pre-submit` | - |
| **Repository** | Read Repo Index | `repo.read_agent_context` | `cat .agent-context.json` | - |
| **Repository** | List Changed Files | `repo.get_changed_files` | - | `git diff --name-only` |
| **Repository** | Read CI Logs | `repo.read_ci_logs` | `td_cli.py repo ci-logs <PR>` | `gh run view` |
| **Repository** | Runtime Check | `repo.doctor` | `td_cli.py doctor` | - |
| **Testing** | Run Vitest | `repo.run_tests` | - | `pnpm test` |
| **Testing** | Run Playwright | `repo.run_playwright` | `td_cli.py repo run-playwright` | `npx playwright test` |
| **Testing** | Run Lighthouse | `repo.run_lighthouse` | - | `npx lhci autorun` |
| **Agent** | Dispatch Jules | `jules.create_session` | `td_cli.py agent dispatch <BRANCH> <TASK>` | - |
| **Agent** | Fix CI | `jules.fix_ci` | `td_cli.py agent fix-ci --pr-number <PR>` | - |
| **Agent** | Sync Sessions | `jules.sync_sessions` | `td_cli.py agent sync` | - |
| **Agent** | Send Message | `jules.send_message` | `td_cli.py agent send <ID> <MSG>` | - |
| **Agent** | Get Messages | `jules.get_messages` | `td_cli.py agent messages <ID>` | - |

---

## 🔍 Code Review Orchestration

The `orchestrateCodeReview` pipeline must source all inputs from MCP tools.
Internal diff-fetching functions (`getCodeDiffSummary`, direct filesystem reads)
must not be called directly — they bypass context injection.

### Required Input Chain (in order)

```
repo.read_agent_context
  → github.get_pr_diff
    → repo.get_changed_files
      → cache check (prevState.cache hash)
        → role gate (file surface check)
          → LLM call (only if no cache hit and role matches surface)
```

### Why This Matters

`.agent-context.json` contains the full `file_tree` and `cli_schema` already
indexed by `boomtick-pkg/scripts/build-repo-context.py`. Using `repo.read_agent_context`
provides pre-indexed structure for free — no redundant filesystem traversal,
no duplicate diff fetches, no re-indexing on every run.

### Role Gating (Token Optimization)

Before dispatching an LLM call, check the changed file surface against the role:

| Role | Only run if changed files include... |
| :--- | :--- |
| `SECURITY` | auth, token, secret, key, crypto, jwt, `.env`, `.pem` surface |
| `PERFORMANCE` | `.ts`, `.tsx`, `.js` files (skip for doc/config-only PRs) |
| `STYLE` | any `src/` files |
| `ARCHITECTURE` | structural files: `package.json`, `vite.config`, `tsconfig`, `src/` |

Early exit: if 2+ roles return `fail`, skip remaining roles — the PR is already
blocked and further LLM calls add no value.

---

## 🛠️ MCP Tool Usage Guidelines

### Asynchronous Operations
Always prefer MCP tools for heavy operations (running tests, fetching large
diffs) to avoid blocking the main execution thread and to leverage built-in
timeouts and safety guards.

### Safety and Isolation
Boomtick MCP tools automatically handle isolated worktrees for mutating
operations. Do **not** manually create worktrees via bash if a corresponding
MCP tool (e.g. `repo.create_repair_branch`) is available.

### Redaction and Tokens
MCP tools automatically handle token redaction and authentication. Avoid
passing raw `GITHUB_TOKEN` values in bash commands if an MCP tool can perform
the same action.

### CLI Schema Fallback
If calling Tier 2 directly, read the CLI schema from `.agent-context.json`
rather than guessing flags or running `--help`:

```bash
# Extract schema for a specific subcommand before calling it
cat .agent-context.json | python3 -c "
import json, sys
schema = json.load(sys.stdin)
print(json.dumps(schema['cli_schema']['subcommands']['gh pr-diff'], indent=2))
"
```

This is what `boomtick-mcp` does automatically on every call.
