import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ListResourcesRequestSchema,
  ReadResourceRequestSchema,
  ListPromptsRequestSchema,
  GetPromptRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { config } from "../config.js";
import { createSuccessResult, createErrorResult } from "../lib/result.js";
import { MCP_TOOLS, MCP_PROMPTS, MCP_RESOURCES } from "./definitions.js";
import { healthHandler, HealthCheckInputSchema } from "./tools.js";
import { searchOpenPrsHandler, SearchOpenPrsInputSchema } from "../tools/github.search_open_prs.js";
import { getPrDiffHandler, GetPrDiffInputSchema } from "../tools/github.get_pr_diff.js";
import { getMergeConflictFilesHandler, GetMergeConflictFilesInputSchema } from "../tools/github.get_merge_conflict_files.js";
import { checkoutBranchHandler, CheckoutBranchInputSchema } from "../tools/github.checkout_branch.js";
import { getChangedFilesHandler, GetChangedFilesInputSchema } from "../tools/repo.get_changed_files.js";
import { getPackageScriptsHandler, GetPackageScriptsInputSchema } from "../tools/repo.get_package_scripts.js";
import { getRouteMapHandler, GetRouteMapInputSchema } from "../tools/repo.get_route_map.js";
import { readCiLogsHandler, ReadCiLogsInputSchema } from "../tools/repo.read_ci_logs.js";
import { repoLogsHandler, RepoLogsInputSchema } from "../tools/repo.logs.js";
import { createRepairBranchHandler, CreateRepairBranchInputSchema } from "../tools/repo.create_repair_branch.js";
import { createBranchHandler, CreateBranchInputSchema } from "../tools/repo.create_branch.js";
import { runTestsHandler, RunTestsInputSchema } from "../tools/repo.run_tests.js";
import { runLighthouseHandler, RunLighthouseInputSchema } from "../tools/repo.run_lighthouse.js";
import { runPlaywrightHandler, RunPlaywrightInputSchema } from "../tools/repo.run_playwright.js";
import { commitPatchHandler, CommitPatchInputSchema } from "../tools/repo.commit_patch.js";
import { openReplacementPrHandler, OpenReplacementPrInputSchema } from "../tools/github.open_replacement_pr.js";
import { commentTriageSummaryHandler, CommentTriageSummaryInputSchema } from "../tools/github.comment_triage_summary.js";
import { createPullRequestHandler, CreatePullRequestInputSchema } from "../tools/github.create_pull_request.js";
import { issueViewHandler, IssueViewInputSchema } from "../tools/github.issue_view.js";
import { issueUpdateHandler, IssueUpdateInputSchema } from "../tools/github.issue_update.js";
import { issueCommentHandler, IssueCommentInputSchema } from "../tools/github.issue_comment.js";


import { createJulesSessionHandler, CreateJulesSessionInputSchema } from "../tools/jules/create-session.js";
import { getJulesSessionHandler, GetJulesSessionInputSchema } from "../tools/jules/get-session.js";
import { sendJulesMessageHandler, SendJulesMessageInputSchema } from "../tools/jules/send-message.js";
import { getJulesMessagesHandler, GetJulesMessagesInputSchema } from "../tools/jules/get-messages.js";
import { listJulesSessionsHandler, ListJulesSessionsInputSchema } from "../tools/jules/list-sessions.js";
import { cancelJulesSessionHandler, CancelJulesSessionInputSchema } from "../tools/jules/cancel-session.js";
import { getJulesPullRequestHandler, GetJulesPullRequestInputSchema } from "../tools/jules/get-pr.js";
import { triggerJulesFeedbackHandler, TriggerJulesFeedbackInputSchema } from "../tools/jules/trigger-feedback.js";
import { ddgsSearchHandler, DdgsSearchInputSchema } from "../tools/ddgs.search.js";

import fs from "fs/promises";
import path from "path";
import { spawnSync } from "child_process";
import { fileURLToPath } from "url";

export class BoomtickMCPServer {
  private server: Server;

  constructor() {
    this.server = new Server(
      {
        name: "boomtick-mcp",
        version: "0.1.0",
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

      const agentsDir = path.resolve(config.repoPath, "boomtick-pkg/mcp/src/agents");
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

    this.server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
      const uri = request.params.uri;
      if (uri === "repo://package-json") {
        const content = await fs.readFile(path.join(config.repoPath, "package.json"), "utf-8");
        return {
          contents: [{ uri, mimeType: "application/json", text: content }],
        };
      }
      if (uri === "repo://routes") {
        const routeMap = await getRouteMapHandler({});
        return {
          contents: [{ uri, mimeType: "application/json", text: JSON.stringify(routeMap, null, 2) }],
        };
      }
      if (uri === "repo://design-tokens") {
        const tokensPath = path.join(config.repoPath, "src/styles/design-tokens.ts");
        const content = await fs.readFile(tokensPath, "utf-8");
        return {
          contents: [{ uri, mimeType: "text/typescript", text: content }],
        };
      }
      if (uri.startsWith("repo://diff/")) {
        const prNumber = parseInt(uri.split("/").pop() || "");
        const diff = await getPrDiffHandler({ prNumber });
        return {
          contents: [{ uri, mimeType: "text/plain", text: diff.diffText }],
        };
      }
      if (uri.startsWith("repo://ci/")) {
        const prNumber = parseInt(uri.split("/").pop() || "");
        const logs = await readCiLogsHandler({ prNumber });
        return {
          contents: [{ uri, mimeType: "application/json", text: JSON.stringify(logs, null, 2) }],
        };
      }
      if (uri.startsWith("repo://lighthouse/")) {
        const branch = uri.split("/").pop() || "";
        const report = await runLighthouseHandler({ route: "/", worktreePath: `../boomtick-mcp-rescue-${branch}` });
        return {
          contents: [{ uri, mimeType: "application/json", text: JSON.stringify(report, null, 2) }],
        };
      }
      if (uri.startsWith("repo://playwright/")) {
        const branch = uri.split("/").pop() || "";
        const report = await runPlaywrightHandler({ worktreePath: `../boomtick-mcp-rescue-${branch}` });
        return {
          contents: [{ uri, mimeType: "application/json", text: JSON.stringify(report, null, 2) }],
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
        switch (request.params.name) {
          case "boomtick.health":
            return createSuccessResult(await healthHandler(HealthCheckInputSchema.parse(request.params.arguments || {})));
          case "github.search_open_prs":
            return createSuccessResult(await searchOpenPrsHandler(SearchOpenPrsInputSchema.parse(request.params.arguments || {})));
          case "github.get_pr_diff":
            return createSuccessResult(await getPrDiffHandler(GetPrDiffInputSchema.parse(request.params.arguments)));
          case "github.get_merge_conflict_files":
            return createSuccessResult(await getMergeConflictFilesHandler(GetMergeConflictFilesInputSchema.parse(request.params.arguments)));
          case "github.checkout_branch":
            return createSuccessResult(await checkoutBranchHandler(CheckoutBranchInputSchema.parse(request.params.arguments)));
          case "repo.get_changed_files":
            return createSuccessResult(await getChangedFilesHandler(GetChangedFilesInputSchema.parse(request.params.arguments || {})));
          case "repo.get_package_scripts":
            return createSuccessResult(await getPackageScriptsHandler(GetPackageScriptsInputSchema.parse(request.params.arguments || {})));
          case "repo.get_route_map":
            return createSuccessResult(await getRouteMapHandler(GetRouteMapInputSchema.parse(request.params.arguments || {})));
          case "repo.read_ci_logs":
            return createSuccessResult(await readCiLogsHandler(ReadCiLogsInputSchema.parse(request.params.arguments)));
          case "repo.logs":
            return createSuccessResult(await repoLogsHandler(RepoLogsInputSchema.parse(request.params.arguments)));
          case "repo.create_branch":
            return createSuccessResult(await createBranchHandler(CreateBranchInputSchema.parse(request.params.arguments)));
          case "repo.create_repair_branch":
            return createSuccessResult(await createRepairBranchHandler(CreateRepairBranchInputSchema.parse(request.params.arguments)));
          case "repo.run_tests":
            return createSuccessResult(await runTestsHandler(RunTestsInputSchema.parse(request.params.arguments || {})));
          case "repo.run_lighthouse":
            return createSuccessResult(await runLighthouseHandler(RunLighthouseInputSchema.parse(request.params.arguments || {})));
          case "repo.run_playwright":
            return createSuccessResult(await runPlaywrightHandler(RunPlaywrightInputSchema.parse(request.params.arguments || {})));
          case "repo.commit_patch":
            return createSuccessResult(await commitPatchHandler(CommitPatchInputSchema.parse(request.params.arguments)));
          case "github.open_replacement_pr":
            return createSuccessResult(await openReplacementPrHandler(OpenReplacementPrInputSchema.parse(request.params.arguments)));
          case "github.comment_triage_summary":
            return createSuccessResult(await commentTriageSummaryHandler(CommentTriageSummaryInputSchema.parse(request.params.arguments)));
          case "github.create_pull_request":
            return createSuccessResult(await createPullRequestHandler(CreatePullRequestInputSchema.parse(request.params.arguments)));
          case "github.issue_view":
            return createSuccessResult(await issueViewHandler(IssueViewInputSchema.parse(request.params.arguments)));
          case "github.issue_update":
            return createSuccessResult(await issueUpdateHandler(IssueUpdateInputSchema.parse(request.params.arguments)));
          case "github.issue_comment":
            return createSuccessResult(await issueCommentHandler(IssueCommentInputSchema.parse(request.params.arguments)));



          case "jules.create_session":
            return createSuccessResult(await createJulesSessionHandler(CreateJulesSessionInputSchema.parse(request.params.arguments)));
          case "jules.get_session":
            return createSuccessResult(await getJulesSessionHandler(GetJulesSessionInputSchema.parse(request.params.arguments)));
          case "jules.send_message":
            return createSuccessResult(await sendJulesMessageHandler(SendJulesMessageInputSchema.parse(request.params.arguments)));
          case "jules.get_messages":
            return createSuccessResult(await getJulesMessagesHandler(GetJulesMessagesInputSchema.parse(request.params.arguments)));
          case "jules.list_sessions":
            return createSuccessResult(await listJulesSessionsHandler(ListJulesSessionsInputSchema.parse(request.params.arguments || {})));
          case "jules.cancel_session":
            return createSuccessResult(await cancelJulesSessionHandler(CancelJulesSessionInputSchema.parse(request.params.arguments)));
          case "jules.get_pr":
            return createSuccessResult(await getJulesPullRequestHandler(GetJulesPullRequestInputSchema.parse(request.params.arguments)));
          case "jules.trigger_feedback":
            return createSuccessResult(await triggerJulesFeedbackHandler(TriggerJulesFeedbackInputSchema.parse(request.params.arguments)));
          case "agent.search_ddgs":
            return createSuccessResult(await ddgsSearchHandler(DdgsSearchInputSchema.parse(request.params.arguments)));
          default:
            return createErrorResult(`Tool not found: ${request.params.name}`);
        }
      } catch (error) {
        return createErrorResult(error instanceof Error ? error.message : String(error));
      }
    });
  }

  async run() {
    // Pre-flight check for td-cli
    try {
      const result = spawnSync("td-cli", ["doctor"], { encoding: "utf-8" });
      if (result.status !== 0) {
        throw new Error("td-cli doctor returned non-zero exit code");
      }
      console.error("✅ td-cli verified on PATH");
    } catch (error) {
      console.error("❌ Fatal: td-cli is not resolvable on PATH. MCP tools will fail.");
      console.error("Please ensure dev-tools are installed: pip install -e dev-tools/");
      process.exit(1);
    }

    const __dirname = path.dirname(fileURLToPath(import.meta.url));
    const ddgsScriptPath = path.join(__dirname, "..", "tools", "ddgs_search.py");
    try {
      await fs.access(ddgsScriptPath);
    } catch (err) {
      console.error(`❌ Fatal: ddgs_search.py not found at ${ddgsScriptPath}`);
      process.exit(1);
    }

    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error("Boomtick MCP Server running on stdio");
  }
}
