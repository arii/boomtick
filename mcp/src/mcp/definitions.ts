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
    name: "boomtick.health",
    description: "Check the health and configuration of the MCP server.",
    inputSchema: HealthCheckInputJsonSchema as any,
  },
  {
    name: "github.search_open_prs",
    description: "Search for open pull requests in the repository.",
    inputSchema: SearchPRsInputJsonSchema as any,
  },
  {
    name: "github.get_pr_diff",
    description: "Get the diff and changed files for a pull request.",
    inputSchema: GetPrDiffInputJsonSchema as any,
  },
  {
    name: "github.checkout_branch",
    description: "Checkout a specific branch in the repository or worktree.",
    inputSchema: CheckoutBranchInputJsonSchema as any,
  },
  {
    name: "github.get_merge_conflict_files",
    description: "Detect files that conflict when a PR is merged with the base branch.",
    inputSchema: GetMergeConflictFilesInputJsonSchema as any,
  },
  {
    name: "repo.get_changed_files",
    description: "Get the list of changed files between two refs.",
    inputSchema: GetChangedFilesInputJsonSchema as any,
  },
  {
    name: "repo.get_package_scripts",
    description: "Get the scripts defined in package.json.",
    inputSchema: GetPackageScriptsInputJsonSchema as any,
  },
  {
    name: "repo.get_route_map",
    description: "Get the mapping of routes to content files.",
    inputSchema: GetRouteMapInputJsonSchema as any,
  },
  {
    name: "repo.read_ci_logs",
    description: "Read CI logs for a given pull request.",
    inputSchema: ReadCiLogsInputJsonSchema as any,
  },
  {
    name: "repo.logs",
    description: "Stream or grep combined CI logs for all jobs in a pull request.",
    inputSchema: RepoLogsInputJsonSchema as any,
  },
  {
    name: "repo.create_branch",
    description: "Creates a new clean git branch from a target base branch.",
    inputSchema: CreateBranchInputJsonSchema as any,
  },
  {
    name: "repo.create_repair_branch",
    description: "Creates a fresh worktree and a new repair branch for an existing PR. This isolates the repair work from the main codebase.",
    inputSchema: CreateRepairBranchInputJsonSchema as any,
  },
  {
    name: "repo.run_tests",
    description: "Run repository tests and checks.",
    inputSchema: RunTestsInputJsonSchema as any,
  },
  {
    name: "repo.run_lighthouse",
    description: "Run Lighthouse CI audits.",
    inputSchema: RunLighthouseInputJsonSchema as any,
  },
  {
    name: "repo.run_playwright",
    description: "Run Playwright E2E tests.",
    inputSchema: RunPlaywrightInputJsonSchema as any,
  },
  {
    name: "repo.commit_patch",
    description: "Commit verified repair changes in a worktree.",
    inputSchema: CommitPatchInputJsonSchema as any,
  },
  {
    name: "github.open_replacement_pr",
    description: "Open a new PR that replaces or repairs the original PR.",
    inputSchema: OpenReplacementPrInputJsonSchema as any,
  },
  {
    name: "github.create_pull_request",
    description: "Creates a pull request on GitHub using the MCP server's integrated credentials. Bypasses terminal CLI constraints.",
    inputSchema: CreatePullRequestInputJsonSchema as any,
  },
  {
    name: "github.comment_triage_summary",
    description: "Comment on the original PR with a diagnosis and replacement link.",
    inputSchema: CommentTriageSummaryInputJsonSchema as any,
  },
  {
    name: "github.get_pr",
    description: "Get details of a GitHub PR including title, state, and URLs.",
    inputSchema: GetPrInputJsonSchema as any,
  },
  {
    name: "github.issue_view",
    description: "View details of a GitHub issue including title, body, and state.",
    inputSchema: IssueViewInputJsonSchema as any,
  },
  {
    name: "github.issue_update",
    description: "Update a GitHub issue's body, labels, and/or state.",
    inputSchema: IssueUpdateInputJsonSchema as any,
  },
  {
    name: "github.issue_comment",
    description: "Add a new comment to a GitHub issue.",
    inputSchema: IssueCommentInputJsonSchema as any,
  },
  {
    name: "github.create_issue",
    description: "Create a new GitHub issue.",
    inputSchema: CreateIssueInputJsonSchema as any,
  },
  {
    name: "jules.create_session",
    description: "Create a Jules session that performs work externally and may generate a GitHub pull request.",
    inputSchema: CreateJulesSessionInputJsonSchema as any,
  },
  {
    name: "jules.get_session",
    description: "Get the status and details of a Jules session.",
    inputSchema: JulesSessionIdInputJsonSchema as any,
  },
  {
    name: "jules.send_message",
    description: "Send a message to an active Jules session.",
    inputSchema: JulesSendMessageInputJsonSchema as any,
  },
  {
    name: "jules.get_messages",
    description: "Get the message history of a Jules session.",
    inputSchema: JulesSessionIdInputJsonSchema as any,
  },
  {
    name: "jules.list_sessions",
    description: "List all Jules sessions.",
    inputSchema: JulesListSessionsInputJsonSchema as any,
  },
  {
    name: "jules.cancel_session",
    description: "Cancel an ongoing Jules session.",
    inputSchema: JulesSessionIdInputJsonSchema as any,
  },
  {
    name: "jules.get_pr",
    description: "Get the generated pull request url associated with an active Jules agent session.",
    inputSchema: JulesSessionIdInputJsonSchema as any,
  },
  {
    name: "jules.trigger_feedback",
    description: "Automatically collect CI status/logs for the PR associated with a Jules session and send them back as feedback.",
    inputSchema: JulesSessionIdInputJsonSchema as any,
  },
  {
    name: "agent.search_ddgs",
    description: "Search the web using DuckDuckGo (via ddgs python library).",
    inputSchema: SearchDdgsInputJsonSchema as any,
  },
];
