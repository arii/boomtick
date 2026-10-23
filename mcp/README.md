# Boomtick MCP: PR Rescue + Merge Conflict Agent

A Model Context Protocol (MCP) server designed to empower AI agents with structured access to GitHub Pull Requests, repository state, CI logs, and validation tools.

## Features

### 🛠 Tools
- **GitHub Ops**: Search PRs, get diffs, detect merge conflicts, open replacement PRs, and triage comments.
- **Repo Ops**: Inspect changed files, extract package scripts, map application routes, and read CI logs.
- **Validation**: Isolated repair branch creation, and running verification suites (Tests, Lighthouse, Playwright).
- **Jules Operations**: Create, monitor, and interact with macro-agent Jules sessions.

### 📄 Resources
- `repo://package-json`: Access root package manifest.
- `repo://design-tokens`: Access UI design tokens.
- `repo://diff/{prNumber}`: Access full PR diff text.
- `repo://ci/{prNumber}`: Access detailed CI check results and logs.

### 🧠 Prompts
- `prompt://conflict-scout`: Scout for PRs needing rescue.
- `prompt://pr-consolidation`: Guidelines for analyzing and proposing consolidation of overlapping PRs.
- `prompt://repo-context`: Gather context before repair.
- `prompt://repair-agent`: Apply minimal safe fixes.
- `prompt://verifier-agent`: Prove the repair works.
- `prompt://pr-writer`: Write professional replacement PR summaries.

### 📝 Scripts
- `scripts/create_instructions.sh`: Generates the `pr-consolidation.prompt.md` instructions file based on PR overlaps.

## Safety First
- **Isolated Worktrees**: All repair and merge operations happen in temporary git worktrees to prevent mutating your local working directory.
- **Safe Shell**: All commands are restricted via an allowlist with automatic token redaction and timeouts.
- **Write Guards**: Mutating operations (commits, branch creation, PR opening) require explicit `writeMode: true` or `pushMode: true` flags.

## Setup

### Prerequisites
- Node.js >= 22
- pnpm >= 10
- GitHub CLI (`gh`) authenticated and in your PATH.

### Installation
```bash
cd boomtick-mcp
pnpm install
pnpm build
```

### Installation via MCP Client (e.g. Claude Desktop)
Add the following to your MCP client configuration (e.g. `claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "boomtick": {
      "command": "node",
      "args": ["/absolute/path/to/boomtick-mcp/dist/index.js"],
      "env": {
        "GITHUB_TOKEN": "your_pat",
        "GITHUB_OWNER": "your_org",
        "GITHUB_REPO": "your_repo",
        "BOOMTICK_REPO_PATH": "/absolute/path/to/repo"
      }
    }
  }
}
```

### Configuration
Create a `.env` file in the `boomtick-mcp` directory:
```env
GITHUB_TOKEN=your_pat
GITHUB_OWNER=your_org
GITHUB_REPO=your_repo
BOOMTICK_REPO_PATH=/path/to/repo
```

## Usage

### Stdio Transport
Run the server via stdio (ideal for local CLI workflows and Docker container actions):
```bash
node dist/index.js
```

### Streamable HTTP Transport & Remote Networked Access
For hosted agent harnesses (e.g. Google Gemini Agent endpoints, remote DevAI dashboards) requiring network transport with Bearer token / OAuth 2.1 authentication and RFC 9728 metadata discovery:

```bash
# Run HTTP entrypoint directly
node dist/http.js --port 3000 --bearer-token secret123

# Or via CLI binary entrypoint
boomtick-mcp-http --port 3000 --bearer-token secret123

# Or using environment variables
MCP_TRANSPORT=http PORT=3000 BOOMTICK_MCP_BEARER_TOKEN=secret123 node dist/index.js
```

#### Network Endpoints & RFC 9728 Discovery
- `GET /.well-known/oauth-protected-resource`: OAuth 2.0 / 2.1 Protected Resource Metadata discovery endpoint (RFC 9728).
- `GET /sse`: Server-Sent Events (SSE) stream endpoint for MCP connections (Protected via Bearer token).
- `POST /messages?sessionId=...`: MCP client JSON-RPC message posting endpoint (Protected via Bearer token).

## Release Process
1. Run tests: `pnpm test`
2. Run evals: `pnpm run run-evals`
3. Update version: `pnpm run release:patch` (or `minor`/`major`)
4. Build: `pnpm run build`
5. Push changes and tags.

## Future Roadmap

### ContentOps + Merch Compliance
- `content.validate_affiliate_disclosure`: Ensure Amazon mandatory wording is present.
- `content.check_trademark_risk`: Flag potential trademark issues in blog posts.
- `amazon.validate_affiliate_card`: Verify affiliate links and product names match media.

### UX Regression + Spec-Driven Redesign
- `ux.capture_screenshot`: Capture multi-viewport screenshots.
- `ux.compare_screenshots`: Detect visual regressions using Playwright.
- `ux.run_accessibility_check`: Automated Axe-core audits.

## Development
- **Build**: `pnpm run build`
- **Test**: `pnpm test`
- **Verify**: `pnpm run run-evals`

For detailed verification steps, see [docs/testing.md](./docs/testing.md).
