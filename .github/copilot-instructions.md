# Boomtick repository instructions

## Repository model

- This is a pnpm workspace with three packages: `mcp`, `workflows`, and the Python `cli` package.
- `mcp/` is the public MCP server. Entry points are `mcp/src/index.ts` (stdio) and `mcp/src/http.ts` (HTTP/SSE). Tool registration and protocol definitions live in `mcp/src/mcp/`; concrete operations live in `mcp/src/tools/`.
- `workflows/` contains the LangGraph.js workflow registry and deterministic workflow implementations used by the MCP `run_workflow` tool.
- `cli/` is the canonical Python `td` CLI package. Command entry points live in `cli/dev_tools/`; the CLI schema is generated metadata, not source of truth for implementation.
- `lib/`, `src/`, and `scripts/` contain shared review/impact-analysis logic and repository automation. `tests/unit/` contains root TypeScript unit tests.
- `tokens-with-taste/` is a separate Python 3.11+ FastAPI/LLM gateway package with the `twt` entry point.
- `.agent-context.json` is a generated repository index read by MCP and agent tooling. Refresh it after structural changes with `pnpm run agent:prime`.
- `project_config.json` is the repository configuration contract for `github_repo`, review routing, and Vite integration. Do not put credentials there.

## Required workflow

- Consult `.agent-context.json` and `cli/dev_tools/cli-schema.json` before repository or GitHub operations.
- Prefer MCP tools in this order: MCP, `td`, then raw shell. Do not guess or use `--help` to discover `td` flags.
- `td` is the canonical CLI name; `td-cli` and aliases are not supported.
- Use isolated worktrees for repair/merge operations. MCP write operations require explicit write mode.
- Stop on runtime mismatch, missing authentication, stale context, or failed preflight; report the exact mismatch instead of bypassing it.
- Read applicable workflow contracts in `.agents/workflows/` for PR review, UX audit, or CI repair tasks.
- Never edit generated artifacts or credentials directly. Trace generated schemas/dist output back to source and rebuild.
- Run `td preflight` before submitting or finalizing changes.

## Setup and runtime

- One-step setup: `./setup-agent.sh`
- Required runtimes: Node.js 24.x and pnpm 10.28.2. The root package declares these constraints; do not change them for a local fix.
- Python CLI setup: `python3` with the repository `.venv` or the setup script.
- Authentication: set `GITHUB_TOKEN` for GitHub operations. Set `GEMINI_API_KEY` only for Gemini-backed reviews.

## Build, test, and lint

Run root commands from the repository root.

```bash
# Install
pnpm install --frozen-lockfile

# Context/index
pnpm run agent:prime

# Full tests
pnpm test
pnpm run test:python
cd tokens-with-taste && python -m pip install '.[test]' && python -m pytest -v

# Full lint/type checks
pnpm run lint
pnpm run type-check
pnpm run type-check:python
pnpm run verify:schemas
td preflight
```

Single-test examples:

```bash
# Root TypeScript Vitest test
pnpm exec vitest run --config vitest.root.config.ts tests/unit/projectConfig.test.ts

# MCP test
cd mcp && pnpm exec vitest run src/tools/github.pr.test.ts

# MCP package test and build
pnpm --filter @arii/boomtick-mcp run test
pnpm --filter @arii/boomtick-mcp run build

# Workflow package test
pnpm --filter @arii/boomtick-workflows run test

# Python CLI test
python3 scripts/run-python-tool.py pytest cli/tests/test_config.py

# Tokens-with-Taste test
cd tokens-with-taste && python -m pytest tests/test_gateway.py
```

Root `pnpm test` combines root Vitest, MCP Vitest, and workflow Vitest suites. Python CLI tests default to `cli/tests`. Root lint runs ESLint, oxlint, Python format/lint/type checks, and the Fallow audit; use the narrow package or test command while iterating.

## Architecture conventions

- MCP source uses ESM `import`/`export`. TypeScript tests are named `*.test.ts`; Python tests are named `test_*.py`.
- MCP tool contracts and schemas are generated/synchronized through `mcp/scripts/sync-contracts.ts` and `mcp/scripts/sync-mcp-schemas.ts`. Rebuild workflow contracts before MCP builds or tests when workflow definitions change.
- MCP tool implementations should return the shared result shape and use process guards/shell allowlists for external commands. Mutating GitHub/Git operations must retain write guards.
- Workflow behavior belongs in `workflows/src/`; MCP exposes it through the consolidated `run_workflow` gateway rather than duplicating workflow logic.
- Shared AI review logic belongs in `lib/`; orchestration entry points belong in `scripts/` and `src/`. Keep provider/model selection in the shared picker/config paths.
- Python CLI commands and schemas should stay aligned: update CLI implementation and regenerate/verify `cli/dev_tools/cli-schema.json` and `cli/dev_tools/cli-commands-schema.json` through `td`/the verification scripts.
- GitHub Actions and composite-action inputs are integration surfaces. Changes to runtime files, schemas, Docker/package metadata, or action behavior require the relevant verification script from `package.json`.
