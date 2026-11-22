# Gemini round 2026-11-09 — boomtick durability/best-practices/token-spend

Chat: BoomTick Codebase Audit (/app/3cbe675232dab401), chip arii/boomtick attached.

## Durability gaps

| Severity | Area | File/Path | Issue | Fix |
|---|---|---|---|---|
| High | Skill Copies vs Symlinks | mcp/src/lib/skills.ts, cli/dev_tools/services/local_sessions.py | Skills read strictly from .agents/skills/<name>/SKILL.md via fs.readFile. Worktrees under .worktrees/ do not symlink/copy .agents/skills/, so sub-agents in isolated worktrees lose skill definitions unless reading from primary root. | In cli/dev_tools/services/worktrees.py:link_warm_deps(), add .agents/skills to WARM_LINK_DIRS. |
| High | CI Gate Silent Bypass | scripts/verify-scope.py, cli/dev_tools/services/scope_gate.py | check_scope() returns True, [], [] immediately if issue_text empty or unfetchable. In non-PR contexts or when gh issue view fails, scope verification silently passes. | Fail closed under --strict-scope; explicit override flag. |
| Medium | RAG Staleness & Drift | cli/dev_tools/services/vector_store.py, cli/dev_tools/commands/ops.py | update_index() relies on git diff between last_indexed_sha and HEAD. Dirty worktrees / uncommitted edits omitted from index → retrieval drift. | Detect dirty states via git status --porcelain and re-index dirty buffers. |
| Medium | MCP Registration Blindspots | cli/dev_tools/handlers/mcp_installer.py | Host configs target hardcoded legacy paths; if parent dirs don't exist, registration silently skips. | Ensure directory creation on explicit --host, or warn loudly on skip. |
| Medium | Missing Env Fallbacks | mcp/src/config.ts, mcp/src/config/github.ts | githubOwner/githubRepo throw if neither project_config.json nor env vars set, even inside a valid checkout with origin remote. | Derive owner/repo via resolveRepo() from mcp/src/lib/git.ts. |

## Best practices

| Severity | Area | File/Path | Issue | Fix |
|---|---|---|---|---|
| High | Project Separation Violation | design_audit_report.md | Stray UI/UX audit report targeting arii/remote-server committed into boomtick root; pollutes context discovery. | Remove or relocate to remote-server. |
| High | Hardcoded Remote Server Path | mcp/src/config.ts | DEFAULT_STACK_ENV_PATH hardcodes /srv/remote-server/.env inside Boomtick MCP config. | Rely on local .env or STACK_ENV_PATH overrides only. |
| Medium | Linting & Typecheck Gap | package.json, .fallowrc.json | Root lint runs eslint+oxlint, but tsc --noEmit only covers mcp/. lib/ and scripts/ have no typecheck target. | Add root type-check:ts covering lib/ and scripts/. |
| Medium | Missing Python Formatting Tool | package.json, cli/pyproject.toml | Enforces pylint+mypy via scripts/run-python-tool.py but no deterministic formatter (ruff/black) in pre-commit/CI. | Add ruff format --check to scripts and pre-push hook. |
| Low | Duplicate Resource Specifications | lib/resources/visual_guidelines.json, cli/dev_tools/resources/visual_guidelines.json | Identical JSONs synced by bash copy in scripts/ensure-schemas.sh. | Single canonical file. |

## Token-spend cuts

1. RAG RRF + score thresholds (35–50% retrieval-turn saving): cutoff Cosine>0.65 / BM25>0.5, drop chunks <40% of top hit, in vector_store.py.
2. AST-driven prompt pruning (40–60% multi-turn): typed schema state across DAG nodes, changed blocks only, in workflows/ + ContextBuilder/buildCodeReviewPrompt.ts.
3. Scratchpad compaction + sliding windows (25–40%/reflection turn): summarize old entries to JSON diffs, truncate logs, in workflows/context.py.
4. Dynamic system-prompt gating (1,500–2,500 tokens/call): inject review guidelines only into evaluation nodes, in buildCodeReviewPrompt.ts.
