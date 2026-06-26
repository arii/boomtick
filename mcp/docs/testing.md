# Boomtick MCP Testing Plan

This document outlines the steps to verify the Boomtick MCP server functionality locally.

## 1. Automated Unit Tests
Run the unit test suite to verify core tool handlers and utilities.
```bash
cd boomtick-mcp
pnpm test
```
**Expected Result**: All tests in `src/lib/shell.test.ts`, `src/tools/github.search_open_prs.test.ts`, and `src/tools/repo.get_package_scripts.test.ts` should pass.

## 2. Build Verification
Ensure the TypeScript source compiles correctly to ESM.
```bash
cd boomtick-mcp
pnpm run build
```
**Expected Result**: The `dist/` directory is populated with `.js` files and no compilation errors occur.

## 3. Evaluation Suite
Run the internal evaluation runner which simulates tool calls in a real (or mocked) environment.
```bash
cd boomtick-mcp
# Note: Ensure you have a valid .env or appropriate environment variables for repo paths
pnpm run run-evals
```
**Expected Result**:
- Health check returns status "ok".
- Repository scripts are successfully extracted.
- GitHub PR search is attempted (may report auth error if token is missing, which is expected behavior).

## 4. MCP Capability Discovery (JSON-RPC)
Verify that the server correctly registers and exposes its capabilities via the MCP protocol.

### List Tools
```bash
echo '{ "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {} }' | node dist/index.js
```
**Expected Result**: A JSON response containing the registered tools including `jules.create_session`, `jules.get_session`, etc.

### List Resources
```bash
echo '{ "jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {} }' | node dist/index.js
```
**Expected Result**: A JSON response containing 8 resources.

### List Prompts
```bash
echo '{ "jsonrpc": "2.0", "id": 1, "method": "prompts/list", "params": {} }' | node dist/index.js
```
**Expected Result**: A JSON response containing 5 prompts.

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

## 7. Safety Verification (Write Guards)
Verify that mutating tools refuse to run without explicit flags.
```bash
echo '{ "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": { "name": "repo.create_repair_branch", "arguments": { "prNumber": 1 } } }' | node dist/index.js
```
**Expected Result**: An error message stating `writeMode must be true`.
