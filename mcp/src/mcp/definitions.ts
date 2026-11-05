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
  WorktreeCreateInputJsonSchema,
  WorktreeCreateResponseJsonSchema,
  WorktreeListInputJsonSchema,
  WorktreeListResponseJsonSchema,
  WorktreeRemoveInputJsonSchema,
  WorktreeRemoveResponseJsonSchema,
  TdInitAndRagInputJsonSchema,
  TdInitAndRagResponseJsonSchema,
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
  {
    uriTemplate: "repo://repair-report/{branch}",
    name: "Repair Report",
    mimeType: "application/json",
    description: "The validation report for a specific repair branch.",
  },
];

const BASE_MCP_TOOLS: Tool[] = [
  {
    name: "boomtick_health",
    description: "Check the health and configuration of the MCP server.",
    inputSchema: HealthCheckInputJsonSchema as any,
    outputSchema: HealthCheckResponseJsonSchema as any,
  },
  {
    name: "repo_read_agent_context",
    description: "Read the repository index including metadata, model review chains, or multi-repo ecosystem status.",
    inputSchema: ReadAgentContextSchema as any,
    outputSchema: ReadAgentContextResponseJsonSchema as any,
  },
  {
    name: "repo_read_ci_logs",
    description: "Read CI logs for a given pull request.",
    inputSchema: ReadCiLogsInputJsonSchema as any,
    outputSchema: ReadCiLogsResponseJsonSchema as any,
  },
  {
    name: "repo_run_tests",
    description: "Run repository tests and checks.",
    inputSchema: RunTestsInputJsonSchema as any,
    outputSchema: RunTestsResponseJsonSchema as any,
  },
  {
    name: "github_get_pr",
    description: "Get details of a GitHub PR including title, state, and URLs.",
    inputSchema: GetPrInputJsonSchema as any,
    outputSchema: GetPrResponseJsonSchema as any,
  },
  {
    name: "github_issue_view",
    description: "View details of a GitHub issue including title, body, and state.",
    inputSchema: IssueViewInputJsonSchema as any,
    outputSchema: IssueViewResponseJsonSchema as any,
  },
  {
    name: "github_issue_update",
    description: "Update a GitHub issue's body, labels, and/or state.",
    inputSchema: IssueUpdateInputJsonSchema as any,
    outputSchema: IssueUpdateResponseJsonSchema as any,
  },
  {
    name: "github_issue_comment",
    description: "Add a new comment to a GitHub issue.",
    inputSchema: IssueCommentInputJsonSchema as any,
    outputSchema: IssueCommentResponseJsonSchema as any,
  },
  {
    name: "github_create_issue",
    description: "Create a new GitHub issue.",
    inputSchema: CreateIssueInputJsonSchema as any,
    outputSchema: CreateIssueResponseJsonSchema as any,
  },
  {
    name: "agent_submit_pr",
    description: "Submit a branch as a pull request (push + open, draft by default). Agents submit; humans merge.",
    inputSchema: AgentSubmitPrInputJsonSchema as any,
    outputSchema: AgentSubmitPrResponseJsonSchema as any,
  },
  {
    name: "worktree_create",
    description: "Create a managed git worktree under .worktrees for an agent session.",
    inputSchema: WorktreeCreateInputJsonSchema as any,
    outputSchema: WorktreeCreateResponseJsonSchema as any,
  },
  {
    name: "worktree_list",
    description: "List managed git worktrees under .worktrees.",
    inputSchema: WorktreeListInputJsonSchema as any,
    outputSchema: WorktreeListResponseJsonSchema as any,
  },
  {
    name: "worktree_remove",
    description: "Remove a managed git worktree. Refuses dirty trees without force.",
    inputSchema: WorktreeRemoveInputJsonSchema as any,
    outputSchema: WorktreeRemoveResponseJsonSchema as any,
  },
  {
    name: "td_init_and_rag",
    description: "Initialize a repo (fast-forward main, sync deps, index RAG) and optionally query the vector index.",
    inputSchema: TdInitAndRagInputJsonSchema as any,
    outputSchema: TdInitAndRagResponseJsonSchema as any,
  },
  {
    name: "td_validate_issue",
    description: "Validate a design spec file deterministically (exit 0 iff valid).",
    inputSchema: TdValidateIssueInputJsonSchema as any,
    outputSchema: TdValidateIssueResponseJsonSchema as any,
  },
  {
    name: "td_verify_scope",
    description: "Gate worktree changes against a spec file (exit 0 iff in scope).",
    inputSchema: TdVerifyScopeInputJsonSchema as any,
    outputSchema: TdVerifyScopeResponseJsonSchema as any,
  },
  {
    name: "td_audit_worktree",
    description: "Audit worktree changes for slop/AST violations with optional blast-radius impact analysis.",
    inputSchema: TdAuditWorktreeInputJsonSchema as any,
    outputSchema: TdAuditWorktreeResponseJsonSchema as any,
  },
];

export const MCP_TOOLS: Tool[] = BASE_MCP_TOOLS;
