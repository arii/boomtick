# Boomtick MCP Testing Plan

This document outlines the steps to verify the Boomtick MCP server functionality locally.

## 1. Automated Unit Tests
Run the unit test suite to verify core tool handlers and utilities.
```bash
cd mcp
pnpm test
```
**Expected Result**: All tests pass, including `src/lib/shell.test.ts`, `src/tools/github.pr.test.ts`, `src/tools/repo.context.test.ts`, `src/tools/repo.tests.test.ts`, and `src/mcp/server.test.ts`.

## 2. Build Verification
Ensure the TypeScript source compiles correctly to ESM.
```bash
cd mcp
pnpm run build
```
**Expected Result**: The `dist/` directory is populated with `.js` files and no compilation errors occur.

## 3. Evaluation Suite
Run the internal evaluation runner which simulates tool calls in a real (or mocked) environment.
```bash
cd mcp
# Note: Ensure you have a valid .env or appropriate environment variables for repo paths
pnpm run run-evals
```
**Expected Result**:
- Repository context returns server health information.
- Repository scripts are successfully extracted.
- GitHub PR search is attempted (may report auth error if token is missing, which is expected behavior).

## 4. MCP Capability Discovery (JSON-RPC)
Verify that the server correctly registers and exposes its capabilities via the MCP protocol.
Run the commands below from `mcp/`; the server discovers the repository root from the working directory.

### List Tools
```bash
echo '{ "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {} }' | node dist/index.js
```
**Expected Result**: A JSON response containing 12 tools: `repo_context`, `repo_test`, `github_issue`, `github_create_issue`, `github_pr`, `agent_submit_pr`, `td_init`, `td_rag`, `td_validate_issue`, `td_verify_scope`, `td_audit_worktree`, and `run_workflow`. Use `github_pr` with `include: ["diff"]` for PR diffs or `include: ["ciLogs"]` for CI logs.

### List Resources
```bash
echo '{ "jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {} }' | node dist/index.js
```
**Expected Result**: A JSON response containing 16 resources (8 canonical resources and their aliases): agent contract, project configuration, changed files, git status, latest CI run, package JSON, design tokens, and workflow registry. See `src/mcp/definitions.ts` for the URIs. `resources/templates/list` separately exposes 2 templates for PR diffs and CI logs.

### List Prompts
```bash
echo '{ "jsonrpc": "2.0", "id": 1, "method": "prompts/list", "params": {} }' | node dist/index.js
```
**Expected Result**: A JSON response containing 6 prompts: `conflict-scout`, `pr-consolidation`, `repo-context`, `repair-agent`, `verifier-agent`, and `pr-writer`.

## 5. Manual Resource Access
Verify that the server can read repository files via the Resource protocol.
```bash
echo '{ "jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": { "uri": "repo://package-json" } }' | node dist/index.js
```
**Expected Result**: The content of the repository's `package.json` is returned in the `text` field.

## 6. Manual Prompt Access
Verify that agent instructions are correctly retrieved.
```bash
echo '{ "jsonrpc": "2.0", "id": 1, "method": "prompts/get", "params": { "name": "conflict-scout" } }' | node dist/index.js
```
**Expected Result**: The markdown content of `src/agents/conflict-scout.prompt.md` is returned.

## 7. Retired Tool Verification
Verify that retired tools are not callable.
```bash
echo '{ "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": { "name": "repo.create_repair_branch", "arguments": { "prNumber": 1 } } }' | node dist/index.js
```
**Expected Result**: An error result stating `Tool not found: repo.create_repair_branch`.
