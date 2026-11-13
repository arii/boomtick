import { Tool, Prompt, Resource, ResourceTemplate } from "@modelcontextprotocol/sdk/types.js";
import {
  HealthCheckInputJsonSchema,
  HealthCheckResponseJsonSchema,
  ReadCiLogsInputJsonSchema,
  ReadCiLogsResponseJsonSchema,
  RunTestsInputJsonSchema,
  RunTestsResponseJsonSchema,
  GetPrInputJsonSchema,
  GetPrResponseJsonSchema,
  IssueViewInputJsonSchema,
  IssueViewResponseJsonSchema,
  IssueUpdateInputJsonSchema,
  IssueUpdateResponseJsonSchema,
  IssueCommentInputJsonSchema,
  IssueCommentResponseJsonSchema,
  CreateIssueInputJsonSchema,
  CreateIssueResponseJsonSchema,
  ReadAgentContextInputJsonSchema as ReadAgentContextSchema,
  ReadAgentContextResponseJsonSchema,
  AgentSubmitPrInputJsonSchema,
  AgentSubmitPrResponseJsonSchema,
  TdInitInputJsonSchema,
  TdInitResponseJsonSchema,
  TdRagInputJsonSchema,
  TdRagResponseJsonSchema,
  TdValidateIssueInputJsonSchema,
  TdValidateIssueResponseJsonSchema,
  TdVerifyScopeInputJsonSchema,
  TdVerifyScopeResponseJsonSchema,
  TdAuditWorktreeInputJsonSchema,
  TdAuditWorktreeResponseJsonSchema,
} from "../tools/contract.js";

export const MCP_PROMPTS: Prompt[] = [
  {
    name: "conflict-scout",
    description: "Find PRs worth rescuing.",
  },
  {
    name: "pr-consolidation",
    description: "Guidelines for analyzing and proposing consolidation of overlapping PRs.",
  },
  {
    name: "repo-context",
    description: "Gather repository context for a PR.",
  },
  {
    name: "repair-agent",
    description: "Apply the smallest safe fix for a PR.",
  },
  {
    name: "verifier-agent",
    description: "Verify that a repair works.",
  },
  {
    name: "pr-writer",
    description: "Write a summary for a replacement PR.",
  },
];

export const MCP_RESOURCES: Resource[] = [
  {
    uri: "boomtick://workspace/agent-contract",
    name: "Agent Contract",
    mimeType: "text/markdown",
    description: "The agent contract specification file (.agents/AGENT_CONTRACT.md) provided by the 'boomtick' MCP server.",
  },
  {
    uri: "mcp://workspace/agent-contract",
    name: "Agent Contract",
    mimeType: "text/markdown",
    description: "The agent contract specification file (.agents/AGENT_CONTRACT.md) provided by the 'boomtick' MCP server.",
  },
  {
    uri: "boomtick://workspace/project-config",
    name: "Project Configuration",
    mimeType: "application/json",
    description: "The project configuration (project_config.json) provided by the 'boomtick' MCP server.",
  },
  {
    uri: "mcp://workspace/project-config",
    name: "Project Configuration",
    mimeType: "application/json",
    description: "The project configuration (project_config.json) provided by the 'boomtick' MCP server.",
  },
  {
    uri: "boomtick://git/changed-files",
    name: "Git Changed Files",
    mimeType: "application/json",
    description: "List of changed files in the repository provided by the 'boomtick' MCP server.",
  },
  {
    uri: "mcp://git/changed-files",
    name: "Git Changed Files",
    mimeType: "application/json",
    description: "List of changed files in the repository provided by the 'boomtick' MCP server.",
  },
  {
    uri: "boomtick://git/status",
    name: "Git Status",
    mimeType: "application/json",
    description: "Current working directory git status provided by the 'boomtick' MCP server.",
  },
  {
    uri: "mcp://git/status",
    name: "Git Status",
    mimeType: "application/json",
    description: "Current working directory git status provided by the 'boomtick' MCP server.",
  },
  {
    uri: "boomtick://ci/latest-run",
    name: "Latest CI Run",
    mimeType: "application/json",
    description: "Recent CI exit statuses, workflow runs, and annotations provided by the 'boomtick' MCP server.",
  },
  {
    uri: "mcp://ci/latest-run",
    name: "Latest CI Run",
    mimeType: "application/json",
    description: "Recent CI exit statuses, workflow runs, and annotations provided by the 'boomtick' MCP server.",
  },
  {
    uri: "boomtick://repo/package-json",
    name: "package.json",
    mimeType: "application/json",
    description: "The root package.json file of the repository provided by the 'boomtick' MCP server.",
  },
  {
    uri: "repo://package-json",
    name: "package.json",
    mimeType: "application/json",
    description: "The root package.json file of the repository provided by the 'boomtick' MCP server.",
  },
  {
    uri: "boomtick://repo/design-tokens",
    name: "Design Tokens",
    mimeType: "application/json",
    description: "The design tokens used in the repository provided by the 'boomtick' MCP server.",
  },
  {
    uri: "repo://design-tokens",
    name: "Design Tokens",
    mimeType: "application/json",
    description: "The design tokens used in the repository provided by the 'boomtick' MCP server.",
  },
];

export const MCP_RESOURCE_TEMPLATES: ResourceTemplate[] = [
  {
    uriTemplate: "mcp://git/diff/{prNumber}",
    name: "Git PR Diff",
    mimeType: "text/plain",
    description: "Diff and changed files for a pull request.",
  },
  {
    uriTemplate: "mcp://ci/logs/{prNumber}",
    name: "CI Logs",
    mimeType: "application/json",
    description: "CI logs for a pull request.",
  },
];

// The generated contract schemas carry readonly tuples where the MCP
// Tool type wants mutable fields, so every entry funnels through this
// one narrowly-typed adapter instead of a blanket `as any` cast.
function toolEntry(
  name: string,
  description: string,
  inputSchema: unknown,
  outputSchema: unknown,
): Tool {
  return {
    name,
    description,
    inputSchema: inputSchema as Tool["inputSchema"],
    outputSchema: outputSchema as Tool["outputSchema"],
  };
}

// Primary toolset for the Issue/Coder/Auditor lane roles.
const CORE_MCP_TOOLS: Tool[] = [
  toolEntry("boomtick_health", "Check the health and configuration of the MCP server.", HealthCheckInputJsonSchema, HealthCheckResponseJsonSchema),
  toolEntry("repo_read_agent_context", "Read the repository index including metadata, model review chains, or multi-repo ecosystem status.", ReadAgentContextSchema, ReadAgentContextResponseJsonSchema),
  toolEntry("repo_run_tests", "Run repository tests and checks.", RunTestsInputJsonSchema, RunTestsResponseJsonSchema),
  toolEntry("github_issue_view", "View details of a GitHub issue including title, body, and state.", IssueViewInputJsonSchema, IssueViewResponseJsonSchema),
  toolEntry("github_issue_update", "Update a GitHub issue's body, labels, and/or state.", IssueUpdateInputJsonSchema, IssueUpdateResponseJsonSchema),
  toolEntry("github_create_issue", "Create a new GitHub issue.", CreateIssueInputJsonSchema, CreateIssueResponseJsonSchema),
  toolEntry("agent_submit_pr", "Submit a branch as a pull request via the deterministic td agent submit-pr exit node (push + open, draft by default). Agents submit; humans merge.", AgentSubmitPrInputJsonSchema, AgentSubmitPrResponseJsonSchema),
  toolEntry("td_init", "Initialize a repo (fast-forward main, sync deps, index RAG). Query separately with td_rag.", TdInitInputJsonSchema, TdInitResponseJsonSchema),
  toolEntry("td_rag", "Query the RAG vector index without re-running init builds.", TdRagInputJsonSchema, TdRagResponseJsonSchema),
  toolEntry("td_validate_issue", "Validate a design spec file deterministically (exit 0 iff valid).", TdValidateIssueInputJsonSchema, TdValidateIssueResponseJsonSchema),
  toolEntry("td_verify_scope", "Gate worktree changes against a spec file (exit 0 iff in scope).", TdVerifyScopeInputJsonSchema, TdVerifyScopeResponseJsonSchema),
  toolEntry("td_audit_worktree", "Audit worktree changes for slop/AST violations with optional blast-radius impact analysis.", TdAuditWorktreeInputJsonSchema, TdAuditWorktreeResponseJsonSchema),
];

// Demoted surface (#1139 item 1): kept on the wire for diagnostics, but
// out of the primary Issue/Coder/Auditor toolsets. Worktree lifecycle
// moved to the orchestrator (`td worktree` / worktrees.py); do not
// re-add worktree_create/list/remove here.
const EXTENDED_MCP_TOOLS: Tool[] = [
  toolEntry("repo_read_ci_logs", "[Demoted] Read CI logs for a given pull request.", ReadCiLogsInputJsonSchema, ReadCiLogsResponseJsonSchema),
  toolEntry("github_get_pr", "[Demoted] Get details of a GitHub PR including title, state, and URLs.", GetPrInputJsonSchema, GetPrResponseJsonSchema),
  toolEntry("github_issue_comment", "[Demoted] Add a new comment to a GitHub issue.", IssueCommentInputJsonSchema, IssueCommentResponseJsonSchema),
];

export const MCP_TOOLS: Tool[] = [...CORE_MCP_TOOLS, ...EXTENDED_MCP_TOOLS];
