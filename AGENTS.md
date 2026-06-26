# Agent Rules & Runtime Contract

This document defines the rules for writing clean code and the strictly pinned
runtime environment used in this repository.

## 🧠 Core Principle

> **UI code should build UI using standard pieces, and the runtime environment
> must remain consistent.**

---

## 1) Import Order

Always sort imports: React → third-party → internal (`@/`) → relative.

## 2) No Inline Styles

Use Tailwind utility classes. Never use `style={{}}` except for dynamic values
that cannot be expressed as utilities (e.g. CSS custom property injection).

## 3) Component File Structure

```
imports
↓
types / interfaces
↓
component function
↓
export default
```

## 4) Props Interface Naming

Name prop interfaces `<ComponentName>Props`. Export them.

## 5) No `any`

Use `unknown` and narrow, or define a proper type. `any` is a lint error.

## 6) Prefer `const` Arrow Functions for Components

```tsx
// ✅
const MyComponent = ({ title }: MyComponentProps) => { ... }

// ❌
function MyComponent({ title }) { ... }
```

## 7) Event Handler Naming

Prefix with `handle`: `handleClick`, `handleSubmit`, `handleChange`.

## 8) Conditional Rendering

Use ternary or `&&` inline. Do not use `if` statements inside JSX return.

## 9) Key Props

Always provide stable, unique `key` props on mapped elements. Never use array
index as key when the list can reorder.

## 10) No Hardcoded Colors

Use design token classes (`text-primary`, `bg-surface`, etc.) from the Tailwind
config. Never use `text-blue-500` directly.

## 11) Component Size Limit

If a component exceeds ~150 lines, split it. Extract sub-components or hooks.

## 12) Custom Hooks

Extract stateful logic into `use<Name>` hooks in `src/hooks/`. Hooks must not
contain JSX.

## 13) Async in Components

Use `useEffect` + `useState` or a data-fetching hook. Never `async` the
component function itself.

## 14) Error Boundaries

Wrap page-level and async-heavy components in an error boundary.

## 15) Accessibility

- All interactive elements must be keyboard-accessible.
- Images require meaningful `alt` text (or `alt=""` for decorative).
- Use semantic HTML (`<button>`, `<nav>`, `<main>`) over `<div onClick>`.

## 16) Test Coverage

New components require at least a smoke test. New utility functions require
unit tests covering the happy path and one edge case.

## 17) No Direct DOM Manipulation

Do not use `document.querySelector` or `element.style` in React components.
Use refs (`useRef`) when direct DOM access is unavoidable.

## 18) Environment Variables

Access via `import.meta.env.VITE_*`. Never hardcode secrets or API keys.
New env vars must be added to `.env.example`.

## 19) Path Aliases

Use `@/` for `src/` imports. Never use deep relative paths (`../../../`).

## 20) Multi-Agent Coordination

When multiple agents work simultaneously:

- Each agent works on its own branch.
- No agent merges to `main` without CI passing.
- Conflicts are resolved via `td_cli.py gh resolve-conflicts` (Tier 2) or
  the equivalent MCP tool (Tier 1). See `.agents/AGENTS.md` for the full
  tool mapping.
- All agents read `.agent-context.json` before starting work to get current
  repository state.

---

## 21) 🤝 Collaborative GitHub Workflows

Consult `.agents/AGENTS.md` for the **Tooling and MCP Protocol** before
executing any GitHub or repository operation.

### The Execution Chain

`boomtick-mcp` is a thin gateway over `boomtick-pkg/cli/dev_tools/td_cli.py`. Every MCP tool
call automatically:
1. Reads `.agent-context.json` to inject `file_tree` and `cli_schema`
2. Calls the appropriate `td_cli.py` subcommand internally
3. Returns structured output with repo context already attached

Calling `td_cli.py` directly skips step 1. Calling raw bash skips steps 1–2.
Only escalate to a lower tier if the MCP tool is **genuinely unavailable**. If an MCP tool or dev-tool command fails or requires fallback to a lower tier, you MUST document the issue in the CLI Failure Ledger (within `progress_and_next_steps.md`) rather than silently bypassing it.

### CLI Schema Authority

`boomtick-pkg/cli/dev_tools/cli-schema.json` (also embedded in `.agent-context.json` under
`cli_schema`) is the single source of truth for all `td_cli.py` flags.
MCP tools read this automatically. If calling Tier 2 directly, always
read `cli_schema` from `.agent-context.json` first — never guess flags,
never use `--help`.

### Code Review Token Budget

Agents invoking `orchestrateCodeReview` must respect the optimization pipeline:

- Follow the input chain: `repo.read_agent_context` → `github.get_pr_diff` →
  `repo.get_changed_files` → cache check → role gate → LLM call
- Do not dispatch all 4 roles unconditionally — check changed file surface
  first (see role gating table in `.agents/AGENTS.md`)
- Max ~8,000 estimated tokens per batch; split earlier if diff sizes warrant
- A `fail` from SECURITY or ARCHITECTURE is sufficient to block a PR — skip
  STYLE/PERFORMANCE after 2+ failures
- Cache hits (`prevState.cache` hash match) skip the LLM call entirely

### Issue Lifecycle

Before auditing GitHub issues, read `docs/agent/issue-audit-rules.md`. Always
validate issues against the Spec-Driven Issue Template before dispatching Jules.

```bash
# Validate a single issue (dry-run by default)
python3 boomtick-pkg/cli/dev_tools/td_cli.py gh validate-issue --issue-number <N>

# Validate and post results
python3 boomtick-pkg/cli/dev_tools/td_cli.py gh validate-issue --issue-number <N> --post-comments --execute
```

### Setting GitHub Variables

```bash
# Read current value
gh variable get ANY_COUNT_BASELINE

# Update
gh variable set ANY_COUNT_BASELINE --body 42
```

---

## 22) Runtime Environment Contract

Strictly pinned: **Node.js 24.16.0** and **pnpm 10.28.2**.

### Setup & Enforcement

Run `./setup-agent.sh` to bootstrap. This script enforces the contract across
`.node-version`, `package.json`, and `.npmrc`, and configures the git hooks
in `.githooks/` so `.agent-context.json` stays fresh automatically.

```bash
./setup-agent.sh
```

After setup, validate:

```bash
python3 boomtick-pkg/cli/dev_tools/td_cli.py doctor
pnpm run check:runtime-files
```

### Forbidden Actions

- ❌ **No `npm`**: Use `pnpm` exclusively.
- ❌ **No Version Managers**: Do not use `nvm`, `pnpm env`, or `volta` to
  deviate from the pinned versions.
- ❌ **No `.npmrc` Bloat**: Never add `use-node-version` (breaks Vercel).
- ❌ **No Lockfile Deletion**: Do not delete `pnpm-lock.yaml`.

Validation failure = immediate halt. Report mismatches; do not attempt to bypass.

---

## GitHub Actions Runtime Policy

All workflows must use `actions/setup-node` with
`node-version-file: '.node-version'`. Do not hardcode Node versions in
workflow files. Keep GitHub Actions pinned to their latest major versions
(e.g. `actions/checkout@v7`, `docker/setup-buildx-action@v4`).
