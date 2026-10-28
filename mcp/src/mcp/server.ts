import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ListResourcesRequestSchema,
  ListResourceTemplatesRequestSchema,
  ReadResourceRequestSchema,
  ListPromptsRequestSchema,
  GetPromptRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { config } from "../config.js";
import { createSuccessResult, createErrorResult } from "../lib/result.js";
import { MCP_TOOLS, MCP_PROMPTS, MCP_RESOURCES, MCP_RESOURCE_TEMPLATES } from "./definitions.js";
import { normalizeArguments } from "../lib/param_utils.js";
import { healthHandler, HealthCheckInputSchema } from "./tools.js";
import { searchOpenPrsHandler, SearchOpenPrsInputSchema } from "../tools/github.search_open_prs.js";
import { getPrDiffHandler, GetPrDiffInputSchema } from "../tools/github.get_pr_diff.js";
import { getMergeConflictFilesHandler, GetMergeConflictFilesInputSchema } from "../tools/github.get_merge_conflict_files.js";
import { checkoutBranchHandler, CheckoutBranchInputSchema } from "../tools/github.checkout_branch.js";
import { getChangedFilesHandler, GetChangedFilesInputSchema } from "../tools/repo.get_changed_files.js";
import { readAgentContextHandler, ReadAgentContextInputSchema } from "../tools/repo.read_agent_context.js";
import { getCommandSchemaHandler, GetCommandSchemaInputSchema } from "../tools/repo.get_command_schema.js";
import { getPackageScriptsHandler, GetPackageScriptsInputSchema } from "../tools/repo.get_package_scripts.js";
import { readCiLogsHandler, ReadCiLogsInputSchema } from "../tools/repo.read_ci_logs.js";
import { repoLogsHandler, RepoLogsInputSchema } from "../tools/repo.logs.js";
import { getWorkflowRunsHandler, GetWorkflowRunsInputSchema } from "../tools/repo.get_workflow_runs.js";
import { createRepairBranchHandler, CreateRepairBranchInputSchema } from "../tools/repo.create_repair_branch.js";
import { createBranchHandler, CreateBranchInputSchema } from "../tools/repo.create_branch.js";
import { runTestsHandler, RunTestsInputSchema } from "../tools/repo.run_tests.js";
import { checkJulesStatusHandler, CheckJulesStatusInputSchema } from "../tools/repo.check_jules_status.js";
import { commitPatchHandler, CommitPatchInputSchema } from "../tools/repo.commit_patch.js";
import { openReplacementPrHandler, OpenReplacementPrInputSchema } from "../tools/github.open_replacement_pr.js";
import { commentTriageSummaryHandler, CommentTriageSummaryInputSchema } from "../tools/github.comment_triage_summary.js";
import { createPullRequestHandler, CreatePullRequestInputSchema } from "../tools/github.create_pull_request.js";
import { getPrHandler, GetPrInputSchema } from "../tools/github.get_pr.js";
import { getPrReviewsHandler, GetPrReviewsInputSchema } from "../tools/github.get_pr_reviews.js";
import { getPrCommitsHandler, GetPrCommitsInputSchema } from "../tools/github.get_pr_commits.js";
import { issueViewHandler, IssueViewInputSchema } from "../tools/github.issue_view.js";
import { issueUpdateHandler, IssueUpdateInputSchema } from "../tools/github.issue_update.js";
import { issueCommentHandler, IssueCommentInputSchema } from "../tools/github.issue_comment.js";
import { createIssueHandler, CreateIssueInputSchema } from "../tools/github.create_issue.js";


import { createJulesSessionHandler, CreateJulesSessionInputSchema } from "../tools/jules/create-session.js";
import { getJulesSessionHandler, GetJulesSessionInputSchema } from "../tools/jules/get-session.js";
import { sendJulesMessageHandler, SendJulesMessageInputSchema } from "../tools/jules/send-message.js";
import { getJulesMessagesHandler, GetJulesMessagesInputSchema } from "../tools/jules/get-messages.js";
import { listJulesSessionsHandler, ListJulesSessionsInputSchema } from "../tools/jules/list-sessions.js";
import { cancelJulesSessionHandler, CancelJulesSessionInputSchema } from "../tools/jules/cancel-session.js";
import { getJulesPullRequestHandler, GetJulesPullRequestInputSchema } from "../tools/jules/get-pr.js";
import { triggerJulesFeedbackHandler, TriggerJulesFeedbackInputSchema } from "../tools/jules/trigger-feedback.js";

import fs from "fs/promises";
import { existsSync, readFileSync } from "fs";
import path from "path";

import { spawnSync } from "child_process";
import { fileURLToPath } from "url";
import { createMcpHttpServer } from "./http.js";

export class BoomtickMCPServer {
  private server: Server;

  constructor() {
    this.server = new Server(
      {
        name: "boomtick-mcp",
        version: "0.2.0",
      },
      {
        capabilities: {
          tools: {},
          resources: {},
          prompts: {},
        },
      }
    );

    this.setupToolHandlers();
    this.setupResourceHandlers();
    this.setupPromptHandlers();
  }

  private setupPromptHandlers() {
    this.server.setRequestHandler(ListPromptsRequestSchema, async () => {
      return {
        prompts: MCP_PROMPTS,
      };
    });

    this.server.setRequestHandler(GetPromptRequestSchema, async (request) => {
      const name = request.params.name;

      const agentsDir = path.resolve(config.repoPath, "mcp/src/agents");
      // nosemgrep
      const promptPath = path.resolve(agentsDir, `${name}.prompt.md`);

      if (!promptPath.startsWith(agentsDir + path.sep)) {
        throw new Error("Path traversal detected");
      }

      try {
        const content = await fs.readFile(promptPath, "utf-8");
        return {
          messages: [
            {
              role: "user",
              content: { type: "text", text: content },
            },
          ],
        };
      } catch (e) {
        throw new Error(`Prompt not found: ${name}`);
      }
    });
  }

  private setupResourceHandlers() {
    this.server.setRequestHandler(ListResourcesRequestSchema, async () => {
      return {
        resources: MCP_RESOURCES,
      };
    });

    this.server.setRequestHandler(ListResourceTemplatesRequestSchema, async () => {
      return {
        resourceTemplates: MCP_RESOURCE_TEMPLATES,
      };
    });

    this.server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
      const uri = request.params.uri;
      if (
        uri === "mcp://workspace/agent-contract" ||
        uri === "mcp://workspace/agent_contract" ||
        uri === "repo://agent-contract"
      ) {
        const contractPath = path.join(config.repoPath, ".agents", "AGENT_CONTRACT.md");
        const content = await fs.readFile(contractPath, "utf-8");
        return {
          contents: [{ uri, mimeType: "text/markdown", text: content }],
        };
      }
      if (
        uri === "mcp://workspace/project-config" ||
        uri === "mcp://workspace/project_config" ||
        uri === "repo://project-config"
      ) {
        const configPath = path.join(config.repoPath, "project_config.json");
        let content = "{}";
        try {
          content = await fs.readFile(configPath, "utf-8");
        } catch {
          // Fallback if file doesn't exist
        }
        return {
          contents: [{ uri, mimeType: "application/json", text: content }],
        };
      }
      if (
        uri === "mcp://git/changed-files" ||
        uri === "repo://changed-files"
      ) {
        const changedFiles = await getChangedFilesHandler(GetChangedFilesInputSchema.parse({}));
        return {
          contents: [{ uri, mimeType: "application/json", text: JSON.stringify(changedFiles, null, 2) }],
        };
      }
      if (
        uri === "mcp://git/status" ||
        uri === "repo://git-status" ||
        uri === "repo://status"
      ) {
        let statusText = "";
        try {
          const res = spawnSync("git", ["status", "--porcelain"], { cwd: config.repoPath, encoding: "utf-8" });
          statusText = res.stdout || "";
        } catch {
          // Fallback if git fails
        }
        return {
          contents: [{ uri, mimeType: "application/json", text: JSON.stringify({ status: statusText.trim() }, null, 2) }],
        };
      }
      if (
        uri === "mcp://ci/latest-run" ||
        uri === "repo://ci/latest-run" ||
        uri === "repo://ci-latest-run"
      ) {
        const workflowRuns = await getWorkflowRunsHandler(GetWorkflowRunsInputSchema.parse({}));
        return {
          contents: [{ uri, mimeType: "application/json", text: JSON.stringify(workflowRuns, null, 2) }],
        };
      }
      if (uri === "repo://package-json" || uri === "mcp://workspace/package-json") {
        const content = await fs.readFile(path.join(config.repoPath, "package.json"), "utf-8");
        return {
          contents: [{ uri, mimeType: "application/json", text: content }],
        };
      }
      if (uri === "repo://design-tokens" || uri === "mcp://workspace/design-tokens") {
        const tokensPath = path.join(config.repoPath, "src/styles/design-tokens.ts");
        const content = await fs.readFile(tokensPath, "utf-8");
        return {
          contents: [{ uri, mimeType: "text/typescript", text: content }],
        };
      }
      if (uri.startsWith("mcp://git/diff/") || uri.startsWith("repo://diff/")) {
        const prNumber = parseInt(uri.split("/").pop() || "");
        const diff = await getPrDiffHandler({ prNumber });
        return {
          contents: [{ uri, mimeType: "text/plain", text: diff.diffText }],
        };
      }
      if (uri.startsWith("mcp://ci/logs/") || uri.startsWith("repo://ci/")) {
        const prNumber = parseInt(uri.split("/").pop() || "");
        const logs = await readCiLogsHandler({ prNumber });
        return {
          contents: [{ uri, mimeType: "application/json", text: JSON.stringify(logs, null, 2) }],
        };
      }
      throw new Error(`Resource not found: ${uri}`);
    });
  }

  private setupToolHandlers() {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => {
      return {
        tools: MCP_TOOLS,
      };
    });

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      try {
        const normalizedToolName = request.params.name.replace(/_/g, ".");
        const normArgs = normalizeArguments(request.params.arguments as Record<string, unknown>);

        switch (normalizedToolName) {
          case "boomtick.health":
            return createSuccessResult(await healthHandler(HealthCheckInputSchema.parse(normArgs)));
          case "github.search.open.prs":
          case "github.search_open_prs":
            return createSuccessResult(await searchOpenPrsHandler(SearchOpenPrsInputSchema.parse(normArgs)));
          case "repo.read.agent.context":
          case "repo.read_agent_context":
            return createSuccessResult(await readAgentContextHandler(ReadAgentContextInputSchema.parse(normArgs)));
          case "github.get.pr.diff":
          case "github.get_pr_diff":
            return createSuccessResult(await getPrDiffHandler(GetPrDiffInputSchema.parse(normArgs)));
          case "github.get.merge.conflict.files":
          case "github.get_merge_conflict_files":
            return createSuccessResult(await getMergeConflictFilesHandler(GetMergeConflictFilesInputSchema.parse(normArgs)));
          case "github.checkout.branch":
          case "github.checkout_branch":
            return createSuccessResult(await checkoutBranchHandler(CheckoutBranchInputSchema.parse(normArgs)));
          case "repo.get.changed.files":
          case "repo.get_changed_files":
            return createSuccessResult(await getChangedFilesHandler(GetChangedFilesInputSchema.parse(normArgs)));
          case "repo.get.command.schema":
          case "repo.get_command_schema":
            return createSuccessResult(await getCommandSchemaHandler(GetCommandSchemaInputSchema.parse(normArgs)));
          case "repo.get.package.scripts":
          case "repo.get_package_scripts":
            return createSuccessResult(await getPackageScriptsHandler(GetPackageScriptsInputSchema.parse(normArgs)));
          case "repo.read.ci.logs":
          case "repo.read_ci_logs":
            return createSuccessResult(await readCiLogsHandler(ReadCiLogsInputSchema.parse(normArgs)));
          case "repo.logs":
            return createSuccessResult(await repoLogsHandler(RepoLogsInputSchema.parse(normArgs)));
          case "repo.get.workflow.runs":
          case "repo.get_workflow_runs":
            return createSuccessResult(await getWorkflowRunsHandler(GetWorkflowRunsInputSchema.parse(normArgs)));
          case "repo.create.branch":
          case "repo.create_branch":
            return createSuccessResult(await createBranchHandler(CreateBranchInputSchema.parse(normArgs)));
          case "repo.create.repair.branch":
          case "repo.create_repair_branch":
            return createSuccessResult(await createRepairBranchHandler(CreateRepairBranchInputSchema.parse(normArgs)));
          case "repo.check.jules.status":
          case "repo.check_jules_status":
            return createSuccessResult(await checkJulesStatusHandler(CheckJulesStatusInputSchema.parse(normArgs)));
          case "repo.run.tests":
          case "repo.run_tests":
            return createSuccessResult(await runTestsHandler(RunTestsInputSchema.parse(normArgs)));
          case "repo.commit.patch":
          case "repo.commit_patch":
            return createSuccessResult(await commitPatchHandler(CommitPatchInputSchema.parse(normArgs)));
          case "github.open.replacement.pr":
          case "github.open_replacement_pr":
            return createSuccessResult(await openReplacementPrHandler(OpenReplacementPrInputSchema.parse(normArgs)));
          case "github.comment.triage.summary":
          case "github.comment_triage_summary":
            return createSuccessResult(await commentTriageSummaryHandler(CommentTriageSummaryInputSchema.parse(normArgs)));
          case "github.create.pull.request":
          case "github.create_pull_request":
            return createSuccessResult(await createPullRequestHandler(CreatePullRequestInputSchema.parse(normArgs)));
          case "github.get.pr":
          case "github.get_pr":
            return createSuccessResult(await getPrHandler(GetPrInputSchema.parse(normArgs)));
          case "github.get.pr.reviews":
          case "github.get_pr_reviews":
            return createSuccessResult(await getPrReviewsHandler(GetPrReviewsInputSchema.parse(normArgs)));
          case "github.get.pr.commits":
          case "github.get_pr_commits":
            return createSuccessResult(await getPrCommitsHandler(GetPrCommitsInputSchema.parse(normArgs)));
          case "github.issue.view":
          case "github.issue_view":
            return createSuccessResult(await issueViewHandler(IssueViewInputSchema.parse(normArgs)));
          case "github.issue.update":
          case "github.issue_update":
            return createSuccessResult(await issueUpdateHandler(IssueUpdateInputSchema.parse(normArgs)));
          case "github.issue.comment":
          case "github.issue_comment":
            return createSuccessResult(await issueCommentHandler(IssueCommentInputSchema.parse(normArgs)));
          case "github.create.issue":
          case "github.create_issue":
            return createSuccessResult(await createIssueHandler(CreateIssueInputSchema.parse(normArgs)));

          case "jules.create.session":
          case "jules.create_session":
            return createSuccessResult(await createJulesSessionHandler(CreateJulesSessionInputSchema.parse(normArgs)));
          case "jules.get.session":
          case "jules.get_session":
            return createSuccessResult(await getJulesSessionHandler(GetJulesSessionInputSchema.parse(normArgs)));
          case "jules.send.message":
          case "jules.send_message":
            return createSuccessResult(await sendJulesMessageHandler(SendJulesMessageInputSchema.parse(normArgs)));
          case "jules.get.messages":
          case "jules.get_messages":
            return createSuccessResult(await getJulesMessagesHandler(GetJulesMessagesInputSchema.parse(normArgs)));
          case "jules.list.sessions":
          case "jules.list_sessions":
            return createSuccessResult(await listJulesSessionsHandler(ListJulesSessionsInputSchema.parse(normArgs)));
          case "jules.cancel.session":
          case "jules.cancel_session":
            return createSuccessResult(await cancelJulesSessionHandler(CancelJulesSessionInputSchema.parse(normArgs)));
          case "jules.get.pr":
          case "jules.get_pr":
            return createSuccessResult(await getJulesPullRequestHandler(GetJulesPullRequestInputSchema.parse(normArgs)));
          case "jules.trigger.feedback":
          case "jules.trigger_feedback":
            return createSuccessResult(await triggerJulesFeedbackHandler(TriggerJulesFeedbackInputSchema.parse(normArgs)));
          default:
            return createErrorResult(`Tool not found: ${request.params.name}`);
        }
      } catch (error) {
        return createErrorResult(error instanceof Error ? error.message : String(error));
      }
    });
  }
  private prepareEnvironmentAndPreflight() {
    const projectRoot = config.repoPath || process.cwd();
    const homeDir = process.env.HOME || "";
    const extraPaths = [];

    // 1. DYNAMIC PYTHON PATH (pip / virtualenv discovery)
    const venvDirs = [".venv", "venv", "env"];
    for (const venvDir of venvDirs) {
      const venvBin = path.join(projectRoot, venvDir, "bin");
      if (existsSync(venvBin)) {
        extraPaths.push(venvBin);
        break;
      }
    }

    // 2. DYNAMIC NODE PATH (.nvmrc parsing)
    const nvmrcPath = path.join(projectRoot, ".nvmrc");
    let targetNodeVersion = "";

    if (existsSync(nvmrcPath)) {
      const rawVersion = readFileSync(nvmrcPath, "utf-8").trim();
      targetNodeVersion = rawVersion.startsWith("v") ? rawVersion : `v${rawVersion}`;
    }

    if (homeDir) {
      extraPaths.push(
        path.join(homeDir, ".local", "bin"),
        path.join(homeDir, "miniforge3", "bin"),
        path.join(homeDir, "anaconda3", "bin"),
        path.join(homeDir, "miniconda3", "bin")
      );

      if (process.env.NVM_BIN) {
        extraPaths.push(process.env.NVM_BIN);
      } else if (targetNodeVersion) {
        extraPaths.push(path.join(homeDir, ".nvm", "versions", "node", targetNodeVersion, "bin"));
      } else {
        extraPaths.push(path.join(homeDir, ".nvm", "versions", "node", process.version, "bin"));
      }
    }

    extraPaths.push(path.dirname(process.execPath));

    const currentPath = process.env.PATH || "";
    const updatedPaths = [...extraPaths, ...currentPath.split(path.delimiter)];
    process.env.PATH = Array.from(new Set(updatedPaths))
      .filter(Boolean)
      .join(path.delimiter);

    // 3. SAFE REPOSITORY RESOLUTION
    const repoPath = config.repoPath || projectRoot;

    // 4. SECURE, UNIX-ONLY PRE-FLIGHT CHECK FOR TD
    try {
      const result = spawnSync("td", ["doctor"], { 
        encoding: "utf-8", 
        cwd: repoPath,
        shell: false // Explicitly disabled to clear Semgrep rules
      });

      if (result.error) {
        throw result.error;
      }

      if (result.status !== 0) {
        console.error("status:", result.status);
        console.error("stdout:", result.stdout);
        console.error("stderr:", result.stderr);
        throw new Error(`td doctor returned exit code: ${result.status}`);
      }

      console.error("✅ td verified on PATH securely");
    } catch (error) {
      console.error("❌ Fatal: td is not resolvable on PATH. MCP tools will fail.");
      console.error("Please ensure the project is installed: pip install -e .");
      console.error("❌ Fatal: td pre-flight check failed:", error instanceof Error ? error.message : String(error));
      process.exit(1);
    }
  }

  async run() {
    this.prepareEnvironmentAndPreflight();

    const args = process.argv.slice(2);
    let port = parseInt(process.env.PORT || process.env.HTTP_PORT || "3000", 10);
    let bearerToken = process.env.BOOMTICK_MCP_BEARER_TOKEN || process.env.MCP_BEARER_TOKEN || process.env.AUTH_TOKEN;

    for (let i = 0; i < args.length; i++) {
      if (args[i] === "--port" && i + 1 < args.length) {
        port = parseInt(args[i + 1], 10);
        i++;
      } else if (args[i].startsWith("--port=")) {
        port = parseInt(args[i].split("=")[1], 10);
      } else if (args[i] === "--bearer-token" && i + 1 < args.length) {
        bearerToken = args[i + 1];
        i++;
      } else if (args[i].startsWith("--bearer-token=")) {
        bearerToken = args[i].split("=")[1];
      }
    }

    const isHttp =
      process.env.MCP_TRANSPORT === "http" ||
      args.includes("--http") ||
      (process.env.PORT !== undefined && !args.includes("--stdio")) ||
      (process.env.HTTP_PORT !== undefined && !args.includes("--stdio"));

    if (isHttp) {
      const mcpHttp = createMcpHttpServer({ port, bearerToken, mcpServer: this.server });
      await mcpHttp.listen(port);
      return;
    }

    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error("Boomtick MCP Server running on stdio");
  }
}
