import { Tool, Prompt, Resource } from "@modelcontextprotocol/sdk/types.js";

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
    inputSchema: {
      type: "object",
      properties: {
        checkDeep: { type: "boolean", description: "Whether to perform a deep health check including external dependencies.", default: false }
      },
      required: []
    },
  },
  {
    name: "github.search_open_prs",
    description: "Search for open pull requests in the repository.",
    inputSchema: {
      type: "object",
      properties: {
        state: { type: "string", enum: ["open", "closed", "all"], default: "open", description: "The state of the PRs to search for (open, closed, all)." },
        includeDrafts: { type: "boolean", default: true, description: "Whether to include draft PRs in the results." },
        limit: { type: "number", minimum: 1, maximum: 100, default: 100, description: "The maximum number of PRs to return (default: 100, range: 1-100)." },
        labels: { type: "array", items: { type: "string" }, description: "Filter PRs by labels." },
      },
      required: [],
    },
  },
  {
    name: "github.get_pr_diff",
    description: "Get the diff and changed files for a pull request.",
    inputSchema: {
      type: "object",
      properties: {
        prNumber: { type: "number", description: "The number of the pull request to get the diff for." },
      },
      required: ["prNumber"],
    },
  },
  {
    name: "github.checkout_branch",
    description: "Checkout a specific branch in the repository or worktree.",
    inputSchema: {
      type: "object",
      properties: {
        branch: { type: "string", description: "The name of the branch to checkout." },
        worktreePath: { type: "string", description: "Optional path to the worktree to perform the checkout in." },
      },
      required: ["branch"],
    },
  },
  {
    name: "github.get_merge_conflict_files",
    description: "Detect files that conflict when a PR is merged with the base branch.",
    inputSchema: {
      type: "object",
      properties: {
        prNumber: { type: "number", description: "The number of the pull request to check for conflicts." },
        baseBranch: { type: "string", default: "main", description: "The base branch to check against (default: 'main')." },
      },
      required: ["prNumber"],
    },
  },
  {
    name: "repo.get_changed_files",
    description: "Get the list of changed files between two refs.",
    inputSchema: {
      type: "object",
      properties: {
        base: { type: "string", default: "main", description: "The base ref to compare from (default: 'main')." },
        head: { type: "string", default: "HEAD", description: "The head ref to compare to (default: 'HEAD')." },
      },
      required: [],
    },
  },
  {
    name: "repo.get_package_scripts",
    description: "Get the scripts defined in package.json.",
    inputSchema: {
      type: "object",
      properties: {
        filter: { type: "string", description: "Optional glob pattern to filter script names." }
      },
      required: []
    },
  },
  {
    name: "repo.get_route_map",
    description: "Get the mapping of routes to content files.",
    inputSchema: {
      type: "object",
      properties: {
        includeStatic: { type: "boolean", description: "Whether to include static assets in the route map." }
      },
      required: []
    },
  },
  {
    name: "repo.read_ci_logs",
    description: "Read CI logs for a given pull request.",
    inputSchema: {
      type: "object",
      properties: {
        prNumber: { type: "number" },
        all: { type: "boolean", description: "Include logs for successful runs (default: false)." },
      },
      required: ["prNumber"],
    },
  },
  {
    name: "repo.logs",
    description: "Stream or grep combined CI logs for all jobs in a pull request.",
    inputSchema: {
      type: "object",
      properties: {
        prNumber: { type: "number" },
        grep: { type: "string", description: "Optional pattern to filter log lines." },
      },
      required: ["prNumber"],
    },
  },
  {
    name: "repo.create_branch",
    description: "Creates a new clean git branch from a target base branch.",
    inputSchema: {
      type: "object",
      properties: {
        branchName: { type: "string", description: "The name of the new branch" },
        baseBranch: { type: "string", default: "main", description: "Branch to branch off from" }
      },
      required: ["branchName"]
    }
  },
  {
    name: "repo.create_repair_branch",
    description: "Creates a fresh worktree and a new repair branch for an existing PR. This isolates the repair work from the main codebase.",
    inputSchema: {
      type: "object",
      properties: {
        prNumber: { type: "number", description: "The original pull request number to repair." },
        repairBranchName: { type: "string", description: "Optional custom name for the new repair branch. Defaults to agent/repair-pr-<num>-<title>." },
        writeMode: { type: "boolean", const: true, description: "Safety gate: Must be true to perform branch creation and worktree setup." },
      },
      required: ["prNumber", "writeMode"],
    },
  },
  {
    name: "repo.run_tests",
    description: "Run repository tests and checks.",
    inputSchema: {
      type: "object",
      properties: {
        commands: { type: "array", items: { type: "string" }, description: "Optional list of commands to run (default includes install, lint, test, build)." },
        timeoutSeconds: { type: "number", default: 300, description: "Maximum time in seconds to wait for tests (default: 300)." },
        worktreePath: { type: "string", description: "Optional path to the worktree to run tests in." },
      },
      required: [],
    },
  },
  {
    name: "repo.run_lighthouse",
    description: "Run Lighthouse CI audits.",
    inputSchema: {
      type: "object",
      properties: {
        route: { type: "string", default: "/", description: "The route to audit (default: '/')." },
        worktreePath: { type: "string", description: "Optional path to the worktree to run the audit in." },
      },
      required: [],
    },
  },
  {
    name: "repo.run_playwright",
    description: "Run Playwright E2E tests.",
    inputSchema: {
      type: "object",
      properties: {
        grep: { type: "string", description: "Optional pattern to filter tests by name." },
        worktreePath: { type: "string", description: "Optional path to the worktree to run tests in." },
      },
      required: [],
    },
  },
  {
    name: "repo.commit_patch",
    description: "Commit verified repair changes in a worktree.",
    inputSchema: {
      type: "object",
      properties: {
        worktreePath: { type: "string", description: "Path to the worktree where changes are made." },
        message: { type: "string", description: "Commit message." },
        allowedFiles: { type: "array", items: { type: "string" }, description: "List of files that are allowed to be committed." },
        writeMode: { type: "boolean", const: true, description: "Safety gate: Must be true to perform the commit." },
      },
      required: ["worktreePath", "message", "allowedFiles", "writeMode"],
    },
  },
  {
    name: "github.open_replacement_pr",
    description: "Open a new PR that replaces or repairs the original PR.",
    inputSchema: {
      type: "object",
      properties: {
        originalPrNumber: { type: "number", description: "The number of the original pull request being replaced." },
        repairBranch: { type: "string", description: "The branch containing the fixes." },
        baseBranch: { type: "string", description: "The branch to merge the fixes into." },
        title: { type: "string", description: "The title of the new PR." },
        body: { type: "string", description: "The body/description of the new PR." },
        draft: { type: "boolean", default: true, description: "Whether to create the PR as a draft (default: true)." },
        worktreePath: { type: "string", description: "Optional path to the worktree where the PR is created from." },
        pushMode: { type: "boolean", const: true, description: "Safety gate: Must be true to push the branch and open the PR." },
      },
      required: ["originalPrNumber", "repairBranch", "baseBranch", "title", "body", "pushMode"],
    },
  },
  {
    name: "github.create_pull_request",
    description: "Creates a pull request on GitHub using the MCP server's integrated credentials. Bypasses terminal CLI constraints.",
    inputSchema: {
      type: "object",
      properties: {
        title: { type: "string", description: "PR Title." },
        body: { type: "string", description: "Description of changes." },
        head: { type: "string", description: "The branch containing changes to merge." },
        base: { type: "string", default: "main", description: "The target branch to merge into." },
        draft: { type: "boolean", default: false, description: "Whether to create the PR as a draft." }
      },
      required: ["title", "body", "head"]
    }
  },
  {
    name: "github.comment_triage_summary",
    description: "Comment on the original PR with a diagnosis and replacement link.",
    inputSchema: {
      type: "object",
      properties: {
        prNumber: { type: "number", description: "The number of the original PR to comment on." },
        body: { type: "string", description: "The content of the comment." },
      },
      required: ["prNumber", "body"],
    },
  },
  {
    name: "github.issue_view",
    description: "View details of a GitHub issue including title, body, and state.",
    inputSchema: {
      type: "object",
      properties: {
        issueNumber: { type: "number", description: "The number of the issue to view." },
      },
      required: ["issueNumber"],
    },
  },
  {
    name: "github.issue_update",
    description: "Update a GitHub issue's body, labels, and/or state.",
    inputSchema: {
      type: "object",
      properties: {
        issueNumber: { type: "number", description: "The number of the issue to update." },
        body: { type: "string", description: "The new body content for the issue." },
        state: { type: "string", description: "The state to set the issue to (open or closed)." },
      },
      required: ["issueNumber"],
    },
  },
  {
    name: "github.issue_comment",
    description: "Add a new comment to a GitHub issue.",
    inputSchema: {
      type: "object",
      properties: {
        issueNumber: { type: "number", description: "The number of the issue to comment on." },
        body: { type: "string", description: "The content of the comment." },
      },
      required: ["issueNumber", "body"],
    },
  },
  {
    name: "github.create_issue",
    description: "Create a new GitHub issue.",
    inputSchema: {
      type: "object",
      properties: {
        title: { type: "string", description: "The title of the issue." },
        body: { type: "string", description: "The body/description of the issue." },
      },
      required: ["title", "body"],
    },
  },
  {
    name: "jules.create_session",
    description: "Create a Jules session that performs work externally and may generate a GitHub pull request.",
    inputSchema: {
      type: "object",
      properties: {
        task: { type: "string", description: "The instructions for Jules." },
        branch: { type: "string", description: "The base branch to start from (e.g., 'main')." },
        pr: { type: "number", description: "The PR number to use as the base branch context." },
      },
      required: ["task"],
    },
  },
  {
    name: "jules.get_session",
    description: "Get the status and details of a Jules session.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "The unique ID of the Jules session." }
      },
      required: ["id"],
    },
  },
  {
    name: "jules.send_message",
    description: "Send a message to an active Jules session.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "The unique ID of the Jules session." },
        message: { type: "string", description: "The message content to send." }
      },
      required: ["id", "message"],
    },
  },
  {
    name: "jules.get_messages",
    description: "Get the message history of a Jules session.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "The unique ID of the Jules session." }
      },
      required: ["id"],
    },
  },
  {
    name: "jules.list_sessions",
    description: "List all Jules sessions.",
    inputSchema: {
      type: "object",
      properties: {
        pageSize: { type: "number", description: "Maximum number of sessions to return." },
        pageToken: { type: "string", description: "Token for pagination." }
      },
      required: []
    },
  },
  {
    name: "jules.cancel_session",
    description: "Cancel an ongoing Jules session.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "The unique ID of the Jules session to cancel." },
      },
      required: ["id"],
    },
  },
  {
    name: "jules.get_pr",
    description: "Get the generated pull request for a Jules session.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "The unique ID of the Jules session." },
      },
      required: ["id"],
    },
  },
  {
    name: "jules.trigger_feedback",
    description: "Automatically collect CI status/logs for the PR associated with a Jules session and send them back as feedback.",
    inputSchema: {
      type: "object",
      properties: {
        sessionId: { type: "string", description: "The unique ID of the Jules session." },
      },
      required: ["sessionId"],
    },
  },
  {
    name: "agent.search_ddgs",
    description: "Search the web using DuckDuckGo (via ddgs python library).",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string" },
        maxResults: { type: "number" },
      },
      required: ["query"],
    },
  },
];
