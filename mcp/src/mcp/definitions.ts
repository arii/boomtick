import { Tool, Prompt, Resource } from "@modelcontextprotocol/sdk/types.js";
import {
  HealthCheckInputJsonSchema,
  SearchPRsInputJsonSchema,
  GetPrDiffInputJsonSchema,
  CheckoutBranchInputJsonSchema,
  GetMergeConflictFilesInputJsonSchema,
  GetChangedFilesInputJsonSchema,
  GetPackageScriptsInputJsonSchema,
  GetRouteMapInputJsonSchema,
  ReadCiLogsInputJsonSchema,
  RepoLogsInputJsonSchema,
  CreateBranchInputJsonSchema,
  CreateRepairBranchInputJsonSchema,
  RunTestsInputJsonSchema,
  RunLighthouseInputJsonSchema,
  RunPlaywrightInputJsonSchema,
  CommitPatchInputJsonSchema,
  OpenReplacementPrInputJsonSchema,
  CreatePullRequestInputJsonSchema,
  CommentTriageSummaryInputJsonSchema,
  GetPrInputJsonSchema,
  IssueViewInputJsonSchema,
  IssueUpdateInputJsonSchema,
  IssueCommentInputJsonSchema,
  CreateIssueInputJsonSchema,
  GetCommandSchemaInputJsonSchema,
  ReadAgentContextInputJsonSchema as ReadAgentContextSchema,
  CreateJulesSessionInputJsonSchema,
  JulesSessionIdInputJsonSchema,
  JulesSendMessageInputJsonSchema,
  JulesListSessionsInputJsonSchema,
  SearchDdgsInputJsonSchema,
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
    uri: "repo://package-json",
    name: "package.json",
    mimeType: "application/json",
    description: "The root package.json file of the repository.",
  },
  {
    uri: "repo://routes",
    name: "Route Map",
    mimeType: "application/json",
    description: "The mapping of application routes to content files.",
  },
  {
    uri: "repo://design-tokens",
    name: "Design Tokens",
    mimeType: "application/json",
    description: "The design tokens used in the repository.",
  },
  {
    uri: "repo://repair-report/{branch}",
    name: "Repair Report",
    mimeType: "application/json",
    description: "The validation report for a specific repair branch.",
  },
  {
    uri: "repo://lighthouse/{branch}",
    name: "Lighthouse Report",
    mimeType: "application/json",
    description: "Lighthouse CI report for a specific branch.",
  },
  {
    uri: "repo://playwright/{branch}",
    name: "Playwright Report",
    mimeType: "application/json",
    description: "Playwright test report for a specific branch.",
  },
];

export const MCP_TOOLS: Tool[] = [
  {
    name: "boomtick_health",
    description: "Check the health and configuration of the MCP server.",
    inputSchema: HealthCheckInputJsonSchema as any,
  },
  {
    name: "github_search_open_prs",
    description: "Search for open pull requests in the repository.",
    inputSchema: SearchPRsInputJsonSchema as any,
  },
  {
    name: "repo_read_agent_context",
    description: "Read the full repository index including file tree, CLI schema, and MCP tools.",
    inputSchema: ReadAgentContextSchema as any,
  },
  {
    name: "github_get_pr_diff",
    description: "Get the diff and changed files for a pull request.",
    inputSchema: GetPrDiffInputJsonSchema as any,
  },
  {
    name: "github_checkout_branch",
    description: "Checkout a specific branch in the repository or worktree.",
    inputSchema: CheckoutBranchInputJsonSchema as any,
  },
  {
    name: "github_get_merge_conflict_files",
    description: "Detect files that conflict when a PR is merged with the base branch.",
    inputSchema: GetMergeConflictFilesInputJsonSchema as any,
  },
  {
    name: "repo_get_changed_files",
    description: "Get the list of changed files between two refs.",
    inputSchema: GetChangedFilesInputJsonSchema as any,
  },
  {
    name: "repo_get_command_schema",
    description: "Retrieve a lightweight, targeted schema for a specific td-cli subcommand. Use this instead of reading the entire cli-schema.json to save tokens.",
    inputSchema: GetCommandSchemaInputJsonSchema as any,
  },
  {
    name: "repo_get_package_scripts",
    description: "Get the scripts defined in package.json.",
    inputSchema: GetPackageScriptsInputJsonSchema as any,
  },
  {
    name: "repo_get_route_map",
    description: "Get the mapping of routes to content files.",
    inputSchema: GetRouteMapInputJsonSchema as any,
  },
  {
    name: "repo_read_ci_logs",
    description: "Read CI logs for a given pull request.",
    inputSchema: ReadCiLogsInputJsonSchema as any,
  },
  {
    name: "repo_logs",
    description: "Stream or grep combined CI logs for all jobs in a pull request.",
    inputSchema: RepoLogsInputJsonSchema as any,
  },
  {
    name: "repo_create_branch",
    description: "Creates a new clean git branch from a target base branch.",
    inputSchema: CreateBranchInputJsonSchema as any,
  },
  {
    name: "repo_create_repair_branch",
    description: "Creates a fresh worktree and a new repair branch for an existing PR. This isolates the repair work from the main codebase.",
    inputSchema: CreateRepairBranchInputJsonSchema as any,
  },
  {
    name: "repo_run_tests",
    description: "Run repository tests and checks.",
    inputSchema: RunTestsInputJsonSchema as any,
  },
  {
    name: "repo_run_lighthouse",
    description: "Run Lighthouse CI audits.",
    inputSchema: RunLighthouseInputJsonSchema as any,
  },
  {
    name: "repo_run_playwright",
    description: "Run Playwright E2E tests.",
    inputSchema: RunPlaywrightInputJsonSchema as any,
  },
  {
    name: "repo_commit_patch",
    description: "Commit verified repair changes in a worktree.",
    inputSchema: CommitPatchInputJsonSchema as any,
  },
  {
    name: "github_open_replacement_pr",
    description: "Open a new PR that replaces or repairs the original PR.",
    inputSchema: OpenReplacementPrInputJsonSchema as any,
  },
  {
    name: "github_create_pull_request",
    description: "Creates a pull request on GitHub using the MCP server's integrated credentials. Bypasses terminal CLI constraints.",
    inputSchema: CreatePullRequestInputJsonSchema as any,
  },
  {
    name: "github_comment_triage_summary",
    description: "Comment on the original PR with a diagnosis and replacement link.",
    inputSchema: CommentTriageSummaryInputJsonSchema as any,
  },
  {
    name: "github_get_pr",
    description: "Get details of a GitHub PR including title, state, and URLs.",
    inputSchema: GetPrInputJsonSchema as any,
  },
  {
    name: "github_issue_view",
    description: "View details of a GitHub issue including title, body, and state.",
    inputSchema: IssueViewInputJsonSchema as any,
  },
  {
    name: "github_issue_update",
    description: "Update a GitHub issue's body, labels, and/or state.",
    inputSchema: IssueUpdateInputJsonSchema as any,
  },
  {
    name: "github_issue_comment",
    description: "Add a new comment to a GitHub issue.",
    inputSchema: IssueCommentInputJsonSchema as any,
  },
  {
    name: "github_create_issue",
    description: "Create a new GitHub issue.",
    inputSchema: CreateIssueInputJsonSchema as any,
  },
  {
    name: "jules_create_session",
    description: "Create a Jules session that performs work externally and may generate a GitHub pull request.",
    inputSchema: CreateJulesSessionInputJsonSchema as any,
  },
  {
    name: "jules_get_session",
    description: "Get the status and details of a Jules session.",
    inputSchema: JulesSessionIdInputJsonSchema as any,
  },
  {
    name: "jules_send_message",
    description: "Send a message to an active Jules session.",
    inputSchema: JulesSendMessageInputJsonSchema as any,
  },
  {
    name: "jules_get_messages",
    description: "Get the message history of a Jules session.",
    inputSchema: JulesSessionIdInputJsonSchema as any,
  },
  {
    name: "jules_list_sessions",
    description: "List all Jules sessions.",
    inputSchema: JulesListSessionsInputJsonSchema as any,
  },
  {
    name: "jules_cancel_session",
    description: "Cancel an ongoing Jules session.",
    inputSchema: JulesSessionIdInputJsonSchema as any,
  },
  {
    name: "jules_get_pr",
    description: "Get the generated pull request url associated with an active Jules agent session.",
    inputSchema: JulesSessionIdInputJsonSchema as any,
  },
  {
    name: "jules_trigger_feedback",
    description: "Automatically collect CI status/logs for the PR associated with a Jules session and send them back as feedback.",
    inputSchema: JulesSessionIdInputJsonSchema as any,
  },
  {
    name: "agent_search_ddgs",
    description: "Search the web using DuckDuckGo (via ddgs python library).",
    inputSchema: SearchDdgsInputJsonSchema as any,
  },
];
