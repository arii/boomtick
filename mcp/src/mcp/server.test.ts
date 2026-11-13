import { describe, it, expect, vi, beforeEach } from "vitest";
import { BoomtickMCPServer } from "./server.js";
import { config } from "../config.js";
import fs from "fs/promises";
import * as healthModule from "./tools.js";
import * as getPrModule from "../tools/github.get_pr.js";
import * as ciLogsModule from "../tools/repo.read_ci_logs.js";
import * as gitLibModule from "../lib/git.js";
import * as tdCliModule from "../lib/tdCli.js";
import * as tdValidateModule from "../tools/td.validate_issue.js";
import * as tdInitModule from "../tools/td.init.js";

vi.mock("fs/promises");
vi.mock("../config.js", () => ({
  config: {
    repoPath: "/mock/repo",
  },
}));

type TestTool = {
  name: string;
  outputSchema: { type: string; properties: Record<string, unknown> };
};

type TestContent = { uri: string; mimeType: string; text: string };

type TestResult = {
  prompts: Array<{ name: string }>;
  resources: Array<{ uri: string }>;
  resourceTemplates: Array<unknown>;
  contents: TestContent[];
  messages: Array<{ role: string; content: { type: string; text: string } }>;
  tools: TestTool[];
  structuredContent: Record<string, unknown>;
  content: Array<{ type: string; text: string }>;
  isError: boolean;
};

type TestHandler = (request: {
  method: string;
  params?: Record<string, unknown>;
}) => Promise<TestResult>;

type TestServerInstance = {
  _requestHandlers?: Map<string, TestHandler>;
  requestHandlers?: Map<string, TestHandler>;
};

describe("BoomtickMCPServer", () => {
  let mcpServer: BoomtickMCPServer;
  let serverInstance: TestServerInstance;
  let requestHandlers: Map<string, TestHandler>;

  beforeEach(() => {
    vi.resetAllMocks();
    requestHandlers = new Map<string, TestHandler>();

    mcpServer = new BoomtickMCPServer();
    serverInstance = (mcpServer as unknown as { server: TestServerInstance }).server;

    // Retrieve registered request handlers from SDK Server instance
    // SDK Server stores request handlers in server._requestHandlers or server.requestHandlers
    const handlers = serverInstance._requestHandlers || serverInstance.requestHandlers;
    if (handlers) {
      for (const [key, handler] of handlers.entries()) {
        requestHandlers.set(key, handler);
      }
    }
  });

  it("should instantiate server with correct name and capabilities", () => {
    expect(serverInstance).toBeDefined();
  });

  describe("ListPrompts", () => {
    it("should return prompts list", async () => {
      const handler = requestHandlers.get("prompts/list");
      expect(handler).toBeDefined();
      const result = await handler!({ method: "prompts/list" });
      expect(result.prompts).toBeDefined();
      expect(Array.isArray(result.prompts)).toBe(true);
    });
  });

  describe("GetPrompt", () => {
    it("should read prompt file and return message", async () => {
      const handler = requestHandlers.get("prompts/get");
      expect(handler).toBeDefined();

      vi.mocked(fs.readFile).mockResolvedValue("You are a helpful agent.");

      const result = await handler!({
        method: "prompts/get",
        params: { name: "test-agent" },
      });

      expect(fs.readFile).toHaveBeenCalledWith("/mock/repo/mcp/src/agents/test-agent.prompt.md", "utf-8");
      expect(result).toEqual({
        messages: [
          {
            role: "user",
            content: { type: "text", text: "You are a helpful agent." },
          },
        ],
      });
    });

    it("should prevent path traversal attacks", async () => {
      const handler = requestHandlers.get("prompts/get");

      await expect(
        handler!({
          method: "prompts/get",
          params: { name: "../../../etc/passwd" },
        })
      ).rejects.toThrow("Path traversal detected");
    });

    it("should throw when prompt file does not exist", async () => {
      const handler = requestHandlers.get("prompts/get");
      vi.mocked(fs.readFile).mockRejectedValue(new Error("File not found"));

      await expect(
        handler!({
          method: "prompts/get",
          params: { name: "nonexistent" },
        })
      ).rejects.toThrow("Prompt not found: nonexistent");
    });
  });

  describe("ListResources", () => {
    it("should return resources list containing workspace resources", async () => {
      const handler = requestHandlers.get("resources/list");
      expect(handler).toBeDefined();
      const result = await handler!({ method: "resources/list" });
      expect(result.resources).toBeDefined();
      expect(Array.isArray(result.resources)).toBe(true);
      const uris = result.resources.map((r: { uri: string }) => r.uri);
      expect(uris).toContain("mcp://workspace/agent-contract");
      expect(uris).toContain("mcp://git/changed-files");
      expect(uris).toContain("mcp://ci/latest-run");
    });

    it("should return resource templates list", async () => {
      const handler = requestHandlers.get("resources/templates/list");
      expect(handler).toBeDefined();
      const result = await handler!({ method: "resources/templates/list" });
      expect(result.resourceTemplates).toBeDefined();
      expect(Array.isArray(result.resourceTemplates)).toBe(true);
    });
  });

  describe("ReadResource", () => {
    it("should handle mcp://workspace/agent-contract", async () => {
      const handler = requestHandlers.get("resources/read");
      vi.mocked(fs.readFile).mockResolvedValue("# Agent Contract\nRule 1");

      const result = await handler!({
        method: "resources/read",
        params: { uri: "mcp://workspace/agent-contract" },
      });

      expect(fs.readFile).toHaveBeenCalledWith("/mock/repo/.agents/AGENT_CONTRACT.md", "utf-8");
      expect(result).toEqual({
        contents: [{ uri: "mcp://workspace/agent-contract", mimeType: "text/markdown", text: "# Agent Contract\nRule 1" }],
      });
    });

    it("should handle mcp://workspace/agent_contract (underscore variant)", async () => {
      const handler = requestHandlers.get("resources/read");
      vi.mocked(fs.readFile).mockResolvedValue("# Agent Contract\nRule 1");

      const result = await handler!({
        method: "resources/read",
        params: { uri: "mcp://workspace/agent_contract" },
      });

      expect(fs.readFile).toHaveBeenCalledWith("/mock/repo/.agents/AGENT_CONTRACT.md", "utf-8");
      expect(result).toEqual({
        contents: [{ uri: "mcp://workspace/agent_contract", mimeType: "text/markdown", text: "# Agent Contract\nRule 1" }],
      });
    });

    it("should handle repo://package-json", async () => {
      const handler = requestHandlers.get("resources/read");
      vi.mocked(fs.readFile).mockResolvedValue('{"name": "test"}');

      const result = await handler!({
        method: "resources/read",
        params: { uri: "repo://package-json" },
      });

      expect(result).toEqual({
        contents: [{ uri: "repo://package-json", mimeType: "application/json", text: '{"name": "test"}' }],
      });
    });

    it("should handle repo://design-tokens", async () => {
      const handler = requestHandlers.get("resources/read");
      vi.mocked(fs.readFile).mockResolvedValue("export const tokens = {};");

      const result = await handler!({
        method: "resources/read",
        params: { uri: "repo://design-tokens" },
      });

      expect(result).toEqual({
        contents: [{ uri: "repo://design-tokens", mimeType: "text/typescript", text: "export const tokens = {};" }],
      });
    });

    it("should handle repo://diff/:prNumber", async () => {
      const handler = requestHandlers.get("resources/read");
      vi.spyOn(getPrModule, "getPrHandler").mockResolvedValue({ diff: { diffText: "diff --git a b" } });

      const result = await handler!({
        method: "resources/read",
        params: { uri: "repo://diff/42" },
      });

      expect(result).toEqual({
        contents: [{ uri: "repo://diff/42", mimeType: "text/plain", text: "diff --git a b" }],
      });
    });

    it("should handle repo://ci/:prNumber", async () => {
      const handler = requestHandlers.get("resources/read");
      vi.spyOn(ciLogsModule, "readCiLogsHandler").mockResolvedValue({ status: "success" });

      const result = await handler!({
        method: "resources/read",
        params: { uri: "repo://ci/42" },
      });

      expect(result.contents[0].uri).toBe("repo://ci/42");
      expect(JSON.parse(result.contents[0].text)).toEqual({ status: "success" });
    });

    it("should handle mcp://git/changed-files", async () => {
      const handler = requestHandlers.get("resources/read");
      vi.spyOn(gitLibModule, "getChangedFiles").mockResolvedValue([
        { status: "M", path: "src/index.ts" },
      ]);

      const result = await handler!({
        method: "resources/read",
        params: { uri: "mcp://git/changed-files" },
      });

      expect(result.contents[0].uri).toBe("mcp://git/changed-files");
      expect(result.contents[0].mimeType).toBe("application/json");
      expect(JSON.parse(result.contents[0].text)).toEqual({ files: [{ status: "M", path: "src/index.ts" }] });
    });

    it("should handle mcp://workspace/project-config", async () => {
      const handler = requestHandlers.get("resources/read");
      vi.mocked(fs.readFile).mockResolvedValue('{"packageName": "boomtick"}');

      const result = await handler!({
        method: "resources/read",
        params: { uri: "mcp://workspace/project-config" },
      });

      expect(result.contents[0].uri).toBe("mcp://workspace/project-config");
      expect(result.contents[0].mimeType).toBe("application/json");
      expect(JSON.parse(result.contents[0].text)).toEqual({ packageName: "boomtick" });
    });

    it("should handle mcp://git/status", async () => {
      const handler = requestHandlers.get("resources/read");

      const result = await handler!({
        method: "resources/read",
        params: { uri: "mcp://git/status" },
      });

      expect(result.contents[0].uri).toBe("mcp://git/status");
      expect(result.contents[0].mimeType).toBe("application/json");
      expect(JSON.parse(result.contents[0].text)).toHaveProperty("status");
    });

    it("should handle mcp://ci/latest-run", async () => {
      const handler = requestHandlers.get("resources/read");
      vi.spyOn(tdCliModule, "runTDCli").mockResolvedValue({ workflow_runs: [{ id: 1, status: "completed", conclusion: "success" }] });

      const result = await handler!({
        method: "resources/read",
        params: { uri: "mcp://ci/latest-run" },
      });

      expect(result.contents[0].uri).toBe("mcp://ci/latest-run");
      expect(result.contents[0].mimeType).toBe("application/json");
      expect(JSON.parse(result.contents[0].text)).toEqual({ workflow_runs: [{ id: 1, status: "completed", conclusion: "success" }] });
    });

    it("should handle boomtick:// URIs", async () => {
      const handler = requestHandlers.get("resources/read");
      vi.mocked(fs.readFile).mockResolvedValue("# Agent Contract\nRule 1");

      const result = await handler!({
        method: "resources/read",
        params: { uri: "boomtick://workspace/agent-contract" },
      });

      expect(fs.readFile).toHaveBeenCalledWith("/mock/repo/.agents/AGENT_CONTRACT.md", "utf-8");
      expect(result.contents[0].uri).toBe("boomtick://workspace/agent-contract");
    });

    it("should throw when resource is unknown", async () => {
      const handler = requestHandlers.get("resources/read");

      await expect(
        handler!({
          method: "resources/read",
          params: { uri: "repo://unknown" },
        })
      ).rejects.toThrow("Resource not found: repo://unknown");
    });
  });

  describe("ListTools", () => {
    it("should return tools list", async () => {
      const handler = requestHandlers.get("tools/list");
      expect(handler).toBeDefined();
      const result = await handler!({ method: "tools/list" });
      expect(result.tools).toBeDefined();
      expect(Array.isArray(result.tools)).toBe(true);
    });

    it("should expose exactly the pruned worktree-safe toolset", async () => {
      const handler = requestHandlers.get("tools/list");
      const result = await handler!({ method: "tools/list" });
      const names = result.tools.map((t: { name: string }) => t.name).sort();
      expect(names).toEqual([
        "agent_submit_pr",
        "boomtick_health",
        "github_create_issue",
        "github_get_pr",
        "github_issue_comment",
        "github_issue_update",
        "github_issue_view",
        "repo_read_agent_context",
        "repo_read_ci_logs",
        "repo_run_tests",
        "td_audit_worktree",
        "td_init",
        "td_rag",
        "td_validate_issue",
        "td_verify_scope",
      ]);
    });

    it("should ensure all tools have typed outputSchema and none are empty or untyped DEFAULT_OUTPUT_SCHEMA", async () => {
      const handler = requestHandlers.get("tools/list");
      const result = await handler!({ method: "tools/list" });
      for (const tool of result.tools) {
        expect(tool.outputSchema).toBeDefined();
        expect(tool.outputSchema.type).toBe("object");
        expect(tool.outputSchema.properties).toBeDefined();
        expect(Object.keys(tool.outputSchema.properties).length).toBeGreaterThan(0);
      }
    });
  });

  describe("CallTool", () => {
    it("should execute registered tool handler successfully", async () => {
      const handler = requestHandlers.get("tools/call");
      vi.spyOn(healthModule, "healthHandler").mockResolvedValue({
        status: "ok",
        config: {
          githubOwner: "o",
          githubRepo: "r",
          repoPath: "/mock/repo",
          readOnly: true,
          ghPath: "gh",
          tdAvailable: true,
        },
      });

      const result = await handler!({
        method: "tools/call",
        params: { name: "boomtick_health", arguments: {} },
      });

      expect(result).toEqual({
        content: [{ type: "text", text: JSON.stringify({ status: "ok", config: { githubOwner: "o", githubRepo: "r", repoPath: "/mock/repo", readOnly: true, ghPath: "gh", tdAvailable: true } }, null, 2) }],
        structuredContent: { status: "ok", config: { githubOwner: "o", githubRepo: "r", repoPath: "/mock/repo", readOnly: true, ghPath: "gh", tdAvailable: true } },
      });
    });

    it("should execute folded github_get_pr includes via underscore or dot name", async () => {
      const handler = requestHandlers.get("tools/call");
      vi.spyOn(getPrModule, "getPrHandler").mockResolvedValue({ pr: { number: 123 }, reviews: [] });

      const res = await handler!({
        method: "tools/call",
        params: { name: "github_get_pr", arguments: { prNumber: 123, includeReviews: true } },
      });
      expect(res.structuredContent).toEqual({ pr: { number: 123 }, reviews: [] });
    });

    it("should return not-found for pruned legacy tools", async () => {
      const handler = requestHandlers.get("tools/call");
      for (const name of [
        "github_get_pr_reviews",
        "github_get_pr_commits",
        "repo_get_workflow_runs",
        "repo_commit_patch",
        "repo_multi_exec",
        "skill_list",
        "skill_read",
        // Worktree lifecycle moved to the orchestrator (issue 1139, item 1).
        "worktree_create",
        "worktree_list",
        "worktree_remove",
      ]) {
        const result = await handler!({
          method: "tools/call",
          params: { name, arguments: {} },
        });
        expect(result.isError).toBe(true);
      }
    });

    it("should execute td_validate_issue", async () => {
      const handler = requestHandlers.get("tools/call");
      vi.spyOn(tdValidateModule, "tdValidateIssueHandler").mockResolvedValue({ valid: true });

      const res = await handler!({
        method: "tools/call",
        params: { name: "td_validate_issue", arguments: { file: "spec.md" } },
      });
      expect(res.structuredContent).toEqual({ valid: true });
    });

    it("should execute td_init split tool (issue 1139, item 2)", async () => {
      const handler = requestHandlers.get("tools/call");
      vi.spyOn(tdInitModule, "tdInitHandler").mockResolvedValue({
        status: "ready",
      });

      const res = await handler!({
        method: "tools/call",
        params: { name: "td_init", arguments: {} },
      });

      expect(res.structuredContent).toEqual({ status: "ready" });
    });

    it("should return error result for unknown tool", async () => {
      const handler = requestHandlers.get("tools/call");

      const result = await handler!({
        method: "tools/call",
        params: { name: "nonexistent.tool", arguments: {} },
      });

      expect(result).toEqual({
        content: [{ type: "text", text: "Tool not found: nonexistent.tool" }],
        isError: true,
      });
    });

    it("should return error result when tool execution throws error", async () => {
      const handler = requestHandlers.get("tools/call");
      vi.spyOn(healthModule, "healthHandler").mockRejectedValue(new Error("Health check failed"));

      const result = await handler!({
        method: "tools/call",
        params: { name: "boomtick_health", arguments: {} },
      });

      expect(result).toEqual({
        content: [{ type: "text", text: "Health check failed" }],
        isError: true,
      });
    });
  });
});
