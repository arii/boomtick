# dev-tools

Developer tooling for the BoomTick repository. The primary entry point is
`td`, but agents should always call `boomtick-mcp` Tier 1 tools first —
`td` is the Tier 2 fallback. See `AGENTS.md` for the full
tool hierarchy.

---

## 🚀 One-Step Setup

```bash
./setup-agent.sh
```

This setup script is now located at the repository root (not symlinked) and handles system tools,
Node.js, pnpm, Python dependencies, Playwright, remote origin configuration,
and git hook registration.

---

## 🔑 Environment Variables

| Variable | Required | Purpose |
| :--- | :--- | :--- |
| `GITHUB_TOKEN` (string) | **Required** | Auth for `gh` and `td gh ...` commands (PR audits, comments, variables, status checks). Standard for GH Actions. |
| `GITHUB_REPOSITORY` (`owner/repo`) | Recommended | Ensures deterministic `origin` remote auto-configuration. |
| `JULES_API_KEY` | Optional | Enables `td agent ...` / `td jules ...` cloud workflows. |
| `GEMINI_API_KEY` | Optional | Enables Gemini-backed review/audit workflows. |

**Secret handling guidance**

- GitHub Actions / agent runners: store `GITHUB_TOKEN`, `JULES_API_KEY`, and
  `GEMINI_API_KEY` in repository or org Secrets.
- Dev containers / local shells: export secrets before running setup/CLI:

```bash
export GITHUB_TOKEN="<token>"
export GITHUB_REPOSITORY="owner/repo"
# optional
export JULES_API_KEY="<key>"
export GEMINI_API_KEY="<key>"
```

**Optional tuning variables**

- `SKIP_GIT_HOOKS=1` — skip git hook execution (e.g. in CI).
- `SKIP_VALIDATION=1` — skip post-setup runtime validation.
- `NODE_MAJOR` — override Node major used for apt installation (defaults to `24`).

---

## 🧩 Workflow-Specific Setup

After `./setup-agent.sh`, use the following workflow-specific setup:

#### 1) Standard PR / Review Workflows

- Plan a review (fetches context and audits):
  - `td agent plan-review --pr <PR_NUMBER>`
- Submit audit results (after authoring the review in `pr-review-<PR>.md`):
  - `td gh audit-pr <PR_NUMBER> --submit --execute`
- Pre-submit quality gate before push/merge:
  - `td gh pre-submit`

#### 2) Jules Workflows

- Required secret: `JULES_API_KEY`.
- Optional context env var: `JULES_SOURCE_ID` (if your environment already
  knows the source mapping).
- Typical commands:
  - `td agent dispatch <BRANCH> "<TASK>"`
  - `td agent fix-ci --pr-number <PR> --execute`
  - `td agent sync`

#### 3) Headless / Bot Auditing

- For batch auditing open PRs:
  - `td gh audit-pr <PR_NUMBER> --fetch --audit --submit --execute`
- Ensure `jq`, `gh`, Python deps, and pnpm deps are installed (handled by
  setup script).

---

## 🗂️ Agent Context Index

`.agent-context.json` (repository root) is the pre-built index that
`boomtick-mcp` reads on every tool call. It contains `file_tree`, `cli_schema`,
and `package_json` metadata — built by `scripts/build-repo-context.py`.

**The index is kept fresh automatically** by the git hooks registered during
`./setup-agent.sh`:

- `.githooks/post-checkout` — refreshes on branch switch
- `.githooks/post-merge` — refreshes on pull/merge

To manually refresh:

```bash
pnpm run agent:prime
```

If the index is stale, MCP tools fall back to raw filesystem calls, bypassing
the index and increasing token usage. Always refresh before running reviews or
dispatching Jules sessions.

---

## 🤖 Agent / Jules GitHub Command Pattern

Always use `boomtick-mcp` Tier 1 tools first. `td` is the fallback
when MCP is unavailable — not the default. See `AGENTS.md` for the
full tool mapping table.

When `td` must be called directly, read the CLI schema from
`.agent-context.json` rather than guessing flags or running `--help`:

```bash
# Extract schema for a specific subcommand before calling it
cat .agent-context.json | python3 -c "
import json, sys
schema = json.load(sys.stdin)
print(json.dumps(schema['cli_schema']['subcommands']['gh pr-diff'], indent=2))
"
```

Prefer repository CLI commands over raw `gh`:

```bash
# ✅ Preferred
td gh <repo-command>

# ⚠️ Only if td does not expose the operation
gh <command>
```

If auth fails, do not run `gh auth login`. Instead, set an environment secret
named `GITHUB_TOKEN`.

---

## ✅ Verification Commands (Post-Setup)

```bash
node --version         # should match .node-version
pnpm --version         # should be 10.28.2
td doctor
pnpm run check:runtime-files
gh auth status
```

---

## 🆘 Troubleshooting

### GitHub CLI not authenticated

```bash
gh issue create --title "<title>" --body "<details>"
```

If auth fails, report this exact issue (do not run interactive auth):

> GitHub CLI is not authenticated. Please add an environment secret named
> `GITHUB_TOKEN` with a repo-scoped GitHub token.

### `.agent-context.json` stale or missing

```bash
pnpm run agent:prime
```

Then re-read before proceeding with any agent operation.

### pnpm / Node mismatch

Stop and report the mismatch. Do not attempt to change runtime versions unless
explicitly instructed to update the runtime contract.

---

## 🚀 Repository CLI (`td`)

`td` is the Tier 2 unified entry point for local repository
automation. All available subcommands and flags are defined in
`cli/dev_tools/cli-schema.json` (also embedded in `.agent-context.json` under
`cli_schema`). That file is the single source of truth — never use `--help`
to discover flags.

Key subcommand groups:

| Group | Description |
| :--- | :--- |
| `doctor` | Runtime consistency check |
| `gh` | GitHub operations (PRs, issues, audits, conflicts) |
| `repo` | Repository operations (CI logs, Playwright) |
| `agent` / `jules` | Jules agent session management |
