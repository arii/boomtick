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
import { checkTdAvailability, recordTdPreflight } from "../lib/tdHealth.js";
import { repoContextHandler, RepoContextInputSchema } from "../tools/repo.context.js";
import { repoTestHandler, RepoTestInputSchema } from "../tools/repo.tests.js";
import { githubPrHandler, GithubPrInputSchema } from "../tools/github.pr.js";
import { githubIssueHandler, GithubIssueInputSchema } from "../tools/github.issue.js";
import { createIssueHandler, CreateIssueInputSchema } from "../tools/github.create_issue.js";
import { tdInitHandler, TdInitInputSchema } from "../tools/td.init.js";
import { tdRagHandler, TdRagInputSchema } from "../tools/td.rag.js";
import { tdValidateIssueHandler, TdValidateIssueInputSchema } from "../tools/td.validate_issue.js";
import { tdVerifyScopeHandler, TdVerifyScopeInputSchema } from "../tools/td.verify_scope.js";
import { tdAuditWorktreeHandler, TdAuditWorktreeInputSchema } from "../tools/td.audit_worktree.js";
import { runWorkflowHandler, describeWorkflowRegistry } from "../tools/run_workflow.js";


import { agentSubmitPrHandler } from "../tools/agent.submit_pr.js";
import { AgentSubmitPrInputSchema, RunWorkflowInputSchema } from "../tools/contract.js";

// NOTE (#1139 item 1): worktree lifecycle moved to the orchestrator
// (`td worktree` / cli/dev_tools/services/worktrees.py). The worktree.*
// MCP tools were deleted; do not re-add them here.
import { getChangedFiles } from "../lib/git.js";
import { runTDCli } from "../lib/tdCli.js";

import fs from "fs/promises";
import { existsSync, readFileSync } from "fs";
import path from "path";

import { spawnSync } from "child_process";
import { fileURLToPath } from "url";
import { createMcpHttpServer } from "./http.js";
import { resolveTransport } from "./transport.js";
import { installProcessGuards } from "../lib/processGuards.js";


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
        uri === "boomtick://workspace/agent-contract" ||
        uri === "mcp://workspace/agent-contract" ||
        uri === "mcp://workspace/agent_contract"
      ) {
        const contractPath = path.join(config.repoPath, ".agents", "AGENT_CONTRACT.md");
        const content = await fs.readFile(contractPath, "utf-8");
        return {
          contents: [{ uri, mimeType: "text/markdown", text: content }],
        };
      }
      if (
        uri === "boomtick://workspace/project-config" ||
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
        uri === "boomtick://git/changed-files" ||
        uri === "mcp://git/changed-files" ||
        uri === "repo://changed-files"
      ) {
        const changedFiles = await getChangedFiles("main", "HEAD", config.repoPath);
        return {
          contents: [{ uri, mimeType: "application/json", text: JSON.stringify({ files: changedFiles }, null, 2) }],
        };
      }
      if (
        uri === "boomtick://git/status" ||
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
        uri === "boomtick://ci/latest-run" ||
        uri === "mcp://ci/latest-run" ||
        uri === "repo://ci/latest-run" ||
        uri === "repo://ci-latest-run"
      ) {
        const workflowRuns = await runTDCli(["repo", "workflow-runs"], "fetch workflow runs");
        return {
          contents: [{ uri, mimeType: "application/json", text: JSON.stringify(workflowRuns, null, 2) }],
        };
      }
      if (uri === "boomtick://repo/package-json" || uri === "repo://package-json" || uri === "mcp://workspace/package-json") {
        const content = await fs.readFile(path.join(config.repoPath, "package.json"), "utf-8");
        return {
          contents: [{ uri, mimeType: "application/json", text: content }],
        };
      }
      if (uri === "boomtick://repo/design-tokens" || uri === "repo://design-tokens" || uri === "mcp://workspace/design-tokens") {
        const tokensPath = path.join(config.repoPath, "src/styles/design-tokens.ts");
        const content = await fs.readFile(tokensPath, "utf-8");
        return {
          contents: [{ uri, mimeType: "text/typescript", text: content }],
        };
      }
      if (uri.startsWith("mcp://git/diff/") || uri.startsWith("repo://diff/")) {
        const prNumber = parseInt(uri.split("/").pop() || "");
        const result = await githubPrHandler({ prNumber, include: ["diff"] });
        const diffPayload = (result as Record<string, unknown>).diff as { diffText?: string } | undefined;
        return {
          contents: [{ uri, mimeType: "text/plain", text: diffPayload?.diffText ?? "" }],
        };
      }
      if (uri.startsWith("mcp://ci/logs/") || uri.startsWith("repo://ci/")) {
        const prNumber = parseInt(uri.split("/").pop() || "");
        const result = await githubPrHandler({ prNumber, include: ["ciLogs"] });
        const logs = (result as Record<string, unknown>).ciLogs ?? {};
        return {
          contents: [{ uri, mimeType: "application/json", text: JSON.stringify(logs, null, 2) }],
        };
      }
      if (uri === "boomtick://workflows/registry" || uri === "mcp://workflows/registry") {
        const registryDescriptor = await describeWorkflowRegistry();
        return {
          contents: [{ uri, mimeType: "application/json", text: JSON.stringify(registryDescriptor, null, 2) }],
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
        const normalizedToolName = request.params.name;
        const normArgs = normalizeArguments(request.params.arguments as Record<string, unknown>);

        switch (normalizedToolName) {
          case "repo_context":
            return createSuccessResult(await repoContextHandler(RepoContextInputSchema.parse(normArgs)));
          case "repo_test":
            return createSuccessResult(await repoTestHandler(RepoTestInputSchema.parse(normArgs)));
          case "github_pr":
            return createSuccessResult(await githubPrHandler(GithubPrInputSchema.parse(normArgs)));
          case "github_issue":
            return createSuccessResult(await githubIssueHandler(GithubIssueInputSchema.parse(normArgs)));
          case "github_create_issue":
            return createSuccessResult(await createIssueHandler(CreateIssueInputSchema.parse(normArgs)));
          case "td_init":
            return createSuccessResult(await tdInitHandler(TdInitInputSchema.parse(normArgs)));
          case "td_rag":
            return createSuccessResult(await tdRagHandler(TdRagInputSchema.parse(normArgs)));
          case "td_validate_issue":
            return createSuccessResult(await tdValidateIssueHandler(TdValidateIssueInputSchema.parse(normArgs)));
          case "td_verify_scope":
            return createSuccessResult(await tdVerifyScopeHandler(TdVerifyScopeInputSchema.parse(normArgs)));
          case "td_audit_worktree":
            return createSuccessResult(await tdAuditWorktreeHandler(TdAuditWorktreeInputSchema.parse(normArgs)));

          case "run_workflow":
            return createSuccessResult(await runWorkflowHandler(RunWorkflowInputSchema.parse(normArgs)));

          case "agent_submit_pr":
            return createSuccessResult(await agentSubmitPrHandler(AgentSubmitPrInputSchema.parse(normArgs)));
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

    // 4. SECURE, UNIX-ONLY PRE-FLIGHT CHECK FOR TD — warn and continue
    // instead of exiting: a missing or broken td degrades the td.* tools
    // and the github tools that shell out to it (github_issue,
    // github_create_issue) but the rest of the server still works. The
    // outcome is surfaced through boomtick_health as the tdAvailable flag.
    const preflight = checkTdAvailability(repoPath);
    recordTdPreflight(preflight);

    if (preflight.available) {
      console.error("✅ td verified on PATH securely");
    } else {
      console.error("⚠️ td pre-flight check failed — td.* and github_issue/github_create_issue tools will degrade:", preflight.reason);
      console.error("Please ensure the project is installed: pip install -e .");
    }
  }

  async run() {
    installProcessGuards();
    this.prepareEnvironmentAndPreflight();

    // Audit H5: HTTP requires an explicit opt-in (--http or
    // MCP_TRANSPORT=http). PORT / HTTP_PORT never flip the transport —
    // service managers export PORT and stdio clients would hang forever.
    const args = process.argv.slice(2);
    const selection = resolveTransport(args);

    if (selection.transport === "http") {
      const mcpHttp = createMcpHttpServer({
        port: selection.port,
        bearerToken: selection.bearerToken,
        mcpServer: this.server,
      });
      await mcpHttp.listen(selection.port);
      return;
    }

    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error("Boomtick MCP Server running on stdio");
  }
}
