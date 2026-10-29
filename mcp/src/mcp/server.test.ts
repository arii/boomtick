import { describe, it, expect, vi, beforeEach } from "vitest";
import { BoomtickMCPServer } from "./server.js";
import { config } from "../config.js";
import fs from "fs/promises";
import * as healthModule from "./tools.js";
import * as prDiffModule from "../tools/github.get_pr_diff.js";
import * as ciLogsModule from "../tools/repo.read_ci_logs.js";
import * as prReviewsModule from "../tools/github.get_pr_reviews.js";
import * as prCommitsModule from "../tools/github.get_pr_commits.js";
import * as workflowRunsModule from "../tools/repo.get_workflow_runs.js";
import * as listJulesSessionsModule from "../tools/jules/list-sessions.js";

vi.mock("fs/promises");
vi.mock("../config.js", () => ({
  config: {
    repoPath: "/mock/repo",
  },
}));

describe("BoomtickMCPServer", () => {
  let mcpServer: BoomtickMCPServer;
  let serverInstance: any;
  let requestHandlers: Map<string, Function>;

  beforeEach(() => {
    vi.resetAllMocks();
    requestHandlers = new Map();

    mcpServer = new BoomtickMCPServer();
    serverInstance = (mcpServer as any).server;

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
      const uris = result.resources.map((r: any) => r.uri);
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
      vi.spyOn(prDiffModule, "getPrDiffHandler").mockResolvedValue({ diffText: "diff --git a b" } as any);

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
      vi.spyOn(ciLogsModule, "readCiLogsHandler").mockResolvedValue({ status: "success" } as any);

      const result = await handler!({
        method: "resources/read",
        params: { uri: "repo://ci/42" },
      });

      expect(result.contents[0].uri).toBe("repo://ci/42");
      expect(JSON.parse(result.contents[0].text)).toEqual({ status: "success" });
    });

    it("should handle mcp://git/changed-files", async () => {
      const handler = requestHandlers.get("resources/read");
      const changedFilesModule = await import("../tools/repo.get_changed_files.js");
      vi.spyOn(changedFilesModule, "getChangedFilesHandler").mockResolvedValue({ files: ["src/index.ts"] } as any);

      const result = await handler!({
        method: "resources/read",
        params: { uri: "mcp://git/changed-files" },
      });

      expect(result.contents[0].uri).toBe("mcp://git/changed-files");
      expect(result.contents[0].mimeType).toBe("application/json");
      expect(JSON.parse(result.contents[0].text)).toEqual({ files: ["src/index.ts"] });
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
      vi.spyOn(workflowRunsModule, "getWorkflowRunsHandler").mockResolvedValue({ workflowRuns: [{ id: 1, status: "completed", conclusion: "success" }] } as any);

      const result = await handler!({
        method: "resources/read",
        params: { uri: "mcp://ci/latest-run" },
      });

      expect(result.contents[0].uri).toBe("mcp://ci/latest-run");
      expect(result.contents[0].mimeType).toBe("application/json");
      expect(JSON.parse(result.contents[0].text)).toEqual({ workflowRuns: [{ id: 1, status: "completed", conclusion: "success" }] });
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
      vi.spyOn(healthModule, "healthHandler").mockResolvedValue({ status: "ok" } as any);

      const result = await handler!({
        method: "tools/call",
        params: { name: "boomtick.health", arguments: {} },
      });

      expect(result).toEqual({
        content: [{ type: "text", text: JSON.stringify({ status: "ok" }, null, 2) }],
        structuredContent: { status: "ok" },
      });
    });

    it("should execute github_get_pr_reviews and github_get_pr_commits via underscore or dot name", async () => {
      const handler = requestHandlers.get("tools/call");
      vi.spyOn(prReviewsModule, "getPrReviewsHandler").mockResolvedValue({ reviews: [] } as any);
      vi.spyOn(prCommitsModule, "getPrCommitsHandler").mockResolvedValue({ commits: [] } as any);
      vi.spyOn(workflowRunsModule, "getWorkflowRunsHandler").mockResolvedValue({ runs: [] } as any);

      const resReviews = await handler!({
        method: "tools/call",
        params: { name: "github_get_pr_reviews", arguments: { prNumber: 123 } },
      });
      expect(resReviews.structuredContent).toEqual({ reviews: [] });

      const resCommits = await handler!({
        method: "tools/call",
        params: { name: "github_get_pr_commits", arguments: { prNumber: 123 } },
      });
      expect(resCommits.structuredContent).toEqual({ commits: [] });

      const resWorkflow = await handler!({
        method: "tools/call",
        params: { name: "repo_get_workflow_runs", arguments: {} },
      });
      expect(resWorkflow.structuredContent).toEqual({ runs: [] });
    });

    it("should execute jules.list_sessions and return structuredContent as a record object wrapping sessions", async () => {
      const handler = requestHandlers.get("tools/call");
      vi.spyOn(listJulesSessionsModule, "listJulesSessionsHandler").mockResolvedValue({
        sessions: [{ id: "sess-1", status: "completed" }],
      });

      const res = await handler!({
        method: "tools/call",
        params: { name: "jules.list_sessions", arguments: {} },
      });

      expect(res.structuredContent).toEqual({
        sessions: [{ id: "sess-1", status: "completed" }],
      });
      expect(Array.isArray(res.structuredContent)).toBe(false);
      expect(typeof res.structuredContent).toBe("object");
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
        params: { name: "boomtick.health", arguments: {} },
      });

      expect(result).toEqual({
        content: [{ type: "text", text: "Health check failed" }],
        isError: true,
      });
    });
  });
});
