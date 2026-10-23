#!/bin/bash

# Ensure label exists
gh label create jules --color "000000" --description "Jules issues" || true

# Issue 1
gh issue create --title "Upgrade Responses to Modern MCP outputSchema & structuredContent" --body "**Current State:** Most tool handlers in \`mcp/src/tools/\` serialize outputs into raw Markdown or plain strings inside \`{ type: \"text\", text }\` content blocks.

**Feedback:** Modern MCP specifications define typed \`outputSchema\` and \`structuredContent\`.

**Action:** Define explicit Zod/JSON schemas for tool responses (e.g., \`github.get_merge_conflict_files\` returning \`{ hasConflicts: boolean, conflictedFiles: string[] }\`, \`repo.run_tests\` returning \`{ passed: boolean, exitCode: number, failedTests: string[] }\`). This allows calling agents (Claude Code, Cursor, Jules) to parse output deterministically without fragile regex parsing." --label jules

# Issue 2
gh issue create --title "Expose Repository State via MCP Resources (Not Just Tools)" --body "**Current State:** Agents inspect git diffs, CI logs, and repository configurations exclusively by executing dynamic tool calls.

**Feedback:** Standard read-only context is better modeled as MCP **Resources**.

**Action:** Expose static and slowly changing workspace context under resource URIs:
* \`mcp://workspace/agent-contract\` (exposing \`.agents/AGENT_CONTRACT.md\`)
* \`mcp://git/changed-files\` (providing active unified diff metadata)
* \`mcp://ci/latest-run\` (exposing recent CI exit statuses and annotations)
This allows host agents to subscribe to workspace state without burning execution turn limits." --label jules

# Issue 3
gh issue create --title "Prepare for Remote/Networked MCP (Streamable HTTP + Auth)" --body "**Current State:** \`mcp/src/index.ts\` only implements \`stdio\` transport.

**Feedback:** While \`stdio\` is ideal for local CLI workflows and Docker container actions, hosted agent harnesses (like Google Gemini Agent endpoints or remote DevAI dashboards like \`RepoAuditor AI\`) require a network transport.

**Action:** Add an optional Streamable HTTP server entrypoint (\`@modelcontextprotocol/server\`) supporting RFC 9728 discovery metadata and Bearer token / OAuth 2.1 validation." --label jules

# Issue 4
gh issue create --title "Implement One-Click GitHub Markdown suggestion Blocks" --body "**Current State:** Reviews post analytical summaries and inline diff feedback as standard Markdown comments.

**Feedback:** Maintainers spend unnecessary time manually copying and applying suggested code changes.

**Action:** Instruct the Gemini review prompt in \`lib/buildCodeReviewPrompt.ts\` to output GitHub suggestion blocks:
\`\`\`markdown
\`\`\`suggestion
const cleanPath = path.normalize(rawPath);
\`\`\`
\`\`\`
Configure the Octokit client to post these suggestions directly on PR diff line ranges so developers can apply fixes with one click directly in GitHub's PR UI." --label jules

# Issue 5
gh issue create --title "Smart Diff Filtering and Token Budgeting" --body "**Current State:** \`scripts/impact-ai-code-review.ts\` and \`lib/codeReviewUtils.ts\` process unified git diffs directly.

**Feedback:** On large PRs, diffs containing generated assets, minified bundles, or lockfile updates (e.g., \`pnpm-lock.yaml\`, \`package-lock.json\`) waste significant context window tokens and risk model hallucination.

**Action:** Add an AST-aware pre-filter in \`lib/codeReviewUtils.ts\` that automatically excludes lockfiles, build outputs, and SVG/binary assets, focusing the token budget strictly on modified business logic and contracts." --label jules

# Issue 6
gh issue create --title "Two-Way Status Reconciliation for Jules Remediation" --body "**Current State:** \`lib/julesReviewClient.ts\` dispatches a failure payload to Jules when a review fails.

**Feedback:** Once dispatched, Boomtick has no visibility into whether Jules succeeded, failed, or timed out.

**Action:** Add a polling or verification task (\`repo.check_jules_status\` or a webhook handler) to confirm when Jules completes its remediation branch, allowing CI pipelines to automatically verify the fix. Include a deterministic idempotency key hash (based on the commit SHA + failure log) to prevent duplicate sessions on rapid re-pushes." --label jules

# Issue 7
gh issue create --title "Semantic AST Linting & Anti-Slop Audits (Tree-sitter)" --body "**Current State:** \`cli/dev_tools/\` contains general scripts and dependency graph analyzers.

**Feedback:** Since \`td\` is your offline, workstation-level governance engine, it should catch subtle code smells before code is pushed to CI.

**Action:** Equip \`td audit\` with \`tree-sitter-typescript\` to catch structural anti-patterns:
* **Design System / Token Bypasses:** Flag raw JSX (\`<div style=\"...\">\`, \`<div className=\"...\">\`) that bypasses shared layout primitives.
* **Type Bypasses:** Flag newly added \`// @ts-ignore\`, \`// @ts-expect-error\`, or \`any\` casts against an approved baseline inventory.
* **Dead Code / AI Scaffolding:** Detect placeholder comments (\`// TODO: implement later\`) or unused mock stubs left by autonomous agents." --label jules

# Issue 8
gh issue create --title "Unified Local Preflight Check (td preflight)" --body "**Feedback:** Developers and agents often run several commands (\`td doctor\`, linting, conflict detection) separately.

**Action:** Provide a single command:
\`\`\`bash
td preflight
\`\`\`
This command should run local typechecks, in-memory merge conflict simulation against \`origin/main\` (\`git merge-tree\`), and multi-PR branch overlap detection before opening a PR." --label jules

# Issue 9
gh issue create --title "Align Multi-Package Publishing via Release Please" --body "**Current State:** Boomtick contains both \`.release-please-manifest.json\` and \`release-please-config.json\`, but packages live across Node (\`mcp/\`), Python (\`cli/\`), and container roots.

**Feedback:** Monorepo multi-language release management frequently experiences version drift if manifests are desynchronized.

**Action:** Ensure \`release-please-config.json\` is configured with component-level versioning so each tier increments independently:
1. **Container Image:** \`ghcr.io/arii/boomtick-review:<tag>\`
2. **npm Package:** \`@arii/boomtick-mcp\`
3. **PyPI Package:** \`boomtick-cli\` (delivering \`td\`)" --label jules
