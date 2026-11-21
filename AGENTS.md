# AGENTS.md — Technical Agent Operating Protocol

This document is the primary contract and tool protocol for AI agents operating within this repository.

---

## 1. Tool Hierarchy & MCP Protocol

Agent tooling in this repository is structured into three tiers:

- **Tier 1 (MCP Protocol - Primary Interface):** When agents run in MCP-compliant hosts (e.g. Claude Code, Cursor, Antigravity CLI), connect to `boomtick-mcp` via `npx @arii/boomtick-mcp` or stdio configuration (`command: "boomtick-mcp"`). Use strongly typed MCP tools for all codebase auditing, PR analysis, and review workflows.
- **Tier 2 (`td` CLI - Secondary/Scripting Interface):** Python analytical CLI in `cli/`. Use `td` for local scripting, automated workflow execution, or as a direct fallback when MCP transport is unavailable.
- **Tier 3 (Raw Shell Commands - Fallback/Execution):** Low-level shell execution (`git`, `pnpm`, `pytest`) for file modifications, build steps, or execution environments.

### Tool Mapping Table

The MCP surface is 11 consolidated tools (schema consolidation 15 → 9/11, feat/mcp-tool-consolidation-15-to-9) plus the `run_workflow` gateway (12 registered): `repo_context`, `repo_test`, `github_issue`, `github_create_issue`, `github_pr`, `agent_submit_pr`, `td_init`, `td_rag`, `td_validate_issue`, `td_verify_scope`, `td_audit_worktree`, `run_workflow`. The retired names (`boomtick_health`, `repo_read_agent_context`, `repo_run_tests`, `github_get_pr`, `github_issue_view`, `github_issue_update`, `github_issue_comment`, `repo_read_ci_logs`, plus the pre-existing dead `github.get_pr_diff`, `github.search_open_prs`, `github.get_merge_conflict_files`) return a "Tool not found" error.

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
| Run Constrained Workflows | `run_workflow` (registry: `boomtick://workflows/registry`) | N/A (workflows package) | N/A |

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
- `tokens-with-taste` — standalone Python 3.11+ LLM gateway and token/cost audit package
- `tests` — automated tests
- `docs` — project documentation
- `src` — application source

## 6. Conventions

- Use ESM `import`/`export` in TypeScript.
- Use `import` and `from ... import` in Python.
- Name TypeScript tests `*.test.ts` and Python tests `test_*.py`.

## 7. ProofLoop Handoff (multi-machine operability)

Branch: `feat/proofloop`. Scoped target: one conflict-warning assist live. No new scope.

### Bring-up (in order)

```sh
cd /home/ari/boomtick && git pull --ff-only  # branch feat/proofloop
set -a && source .env && set +a              # keys live ONLY in root .env; never print or commit it
```

1. Tests (no keys needed): `pnpm run test:proofloop`
2. LLM gateway: `cd tokens-with-taste && twt sync`, then detached:
   `setsid -f bash -c 'set -a; source /home/ari/boomtick/.env; set +a; export TWT_DAILY_BUDGET_USD=5; exec /home/ari/boomtick/.venv/bin/twt serve' </dev/null >>/tmp/twt.log 2>&1`
   Verify: `curl -s http://127.0.0.1:8000/v1/models | head -c 200`
   Pin: `TWT_MODEL=nebius/google/gemma-3-27b-it` (clean JSON, ~$0.00005/call). Kill with `pkill -f '[t]wt serve'` (never bare `twt serve`: it matches your own shell).
3. Health: `cd proofloop/harness && PROOFLOOP_LIVE_SERVICES=twt,senso,cognee PROOFLOOP_ALLOW_SESSION_UPLOAD=1 python3 health.py --probe-live`
4. Tasks (once; file is committed reviewed): `PROOFLOOP_LIVE_SERVICES=twt python3 tasks.py --generate`, review `data/replay_tasks.json`, set `generated.reviewed=true`
5. Loop: `PROOFLOOP_LIVE_SERVICES=twt,senso,cognee PROOFLOOP_ALLOW_SESSION_UPLOAD=1 TWT_MODEL=nebius/google/gemma-3-27b-it python3 replay_loop.py` (resumes from saved state; `--reset` only for a fresh ledger)
6. Backend, detached: `setsid -f bash -c 'set -a; source /home/ari/boomtick/.env; set +a; export PROOFLOOP_EXTENSION_ID=<id from chrome://extensions> TWT_MODEL=nebius/google/gemma-3-27b-it; exec python3 server.py 8787' </dev/null >>/tmp/proofloop-server.log 2>&1`
   Token lands in `proofloop/state/server_token` (git-ignored, mode 600). Verify with it against `/status`.
7. Extension: `chrome://extensions` -> Developer mode -> Load unpacked (or Reload) `proofloop/extension`. Paste token into extension Settings. Toolbar button: "Watch all tabs" (all `http(s)` tabs incl. terminal) or per-site "Watch this site". Reload watched pages.
8. Spend audit: `twt report --since <date>` and `twt audit --flagged`

### Current status (2026-11-20 EOD)

- Done: M1 auto-repeat loop + M2 backend (Kiro); watch-all-tabs + tab snapshot + pause + terminal-light chip + `/assist` `open_tabs`/`tab_matches`/cache (this machine); offline suite green (28 Python + extension + contracts).
- Live: Senso/Cognee/LLM health green; Cognee ingested 8 sessions; loop converged with NO promotion (gemma baseline 0.0; one good proposal held in noise; two rejected on provenance). `/assist` verified with real context on luma.com and boomtick.blog.
- Pending: rerun loop on a stronger Nebius model; provenance fix landed in 99c1116 (failing task's own session is always citable); regenerate tasks with the fixed generator (current suite: 3 tasks, holdout unpassable, see PLAN 0.1); reload extension to v0.5.0 and confirm pill on terminal (127.0.0.1:8082) + a form page.
- Docs: `proofloop/SUBMISSION.md` is current (c68ca1d). `proofloop/TRACKING.md` is current at the top; its older sections are history. `proofloop/PLAN.md` section 0.1 is the audit and next steps.

### Agent orchestration (repeatable)

- Muse (this CLI) is usage-limited: orchestration, reviews, live-machine runs only. Heavy building goes to the free agents.
- Kiro (free credits, slow): https://app.kiro.dev/session/80013a4a-ee1c-4caf-85e3-7218e0e32149. Never message while it shows working/thinking. Needs page reloads. Sandbox has no keys and cannot reach the TWT gateway: it reports live steps as not-run; this machine runs them.
- Instinct (free, headless via WhatsApp): https://web.whatsapp.com/ chat "Instinct". Standing orders: merge each fix once CI passes, then continue. Currently on remote-server track (PRs #1492, #1493 pattern).
- Gemini steering (project direction): https://gemini.google.com/app/2d4704933b77ad46. Applied: multi-tab snapshot design, terminal-light chip, Nebius-under-$5, pre-promotion evidence bar (v0 baseline + improving candidate + clean Senso round-trip + rejected regression).
- Browser control: browser-mcp drives the user's Chrome (tabs above are usually already open). `chrome://` pages cannot be scripted; read extension IDs from `~/.config/google-chrome/Default/Preferences` instead.
- Privacy invariants: keys only from process env; `proofloop/state/*` and `.env` are git-ignored; page values never leave the browser (hashes only); `data/private/` stays local.
