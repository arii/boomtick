import { describe, it, expect, vi, beforeEach } from "vitest";
import { BoomtickMCPServer } from "./server.js";
import { config } from "../config.js";
import fs from "fs/promises";
import * as healthModule from "./tools.js";
import * as routeMapModule from "../tools/repo.get_route_map.js";
import * as prDiffModule from "../tools/github.get_pr_diff.js";
import * as ciLogsModule from "../tools/repo.read_ci_logs.js";
import * as lighthouseModule from "../tools/repo.run_lighthouse.js";
import * as playwrightModule from "../tools/repo.run_playwright.js";

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
    it("should return resources list", async () => {
      const handler = requestHandlers.get("resources/list");
      expect(handler).toBeDefined();
      const result = await handler!({ method: "resources/list" });
      expect(result.resources).toBeDefined();
      expect(Array.isArray(result.resources)).toBe(true);
    });
  });

  describe("ReadResource", () => {
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

    it("should handle repo://routes", async () => {
      const handler = requestHandlers.get("resources/read");
      vi.spyOn(routeMapModule, "getRouteMapHandler").mockResolvedValue({ routes: ["/"] } as any);

      const result = await handler!({
        method: "resources/read",
        params: { uri: "repo://routes" },
      });

      expect(result.contents[0].uri).toBe("repo://routes");
      expect(JSON.parse(result.contents[0].text)).toEqual({ routes: ["/"] });
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

    it("should handle repo://lighthouse/:branch", async () => {
      const handler = requestHandlers.get("resources/read");
      vi.spyOn(lighthouseModule, "runLighthouseHandler").mockResolvedValue({ score: 100 } as any);

      const result = await handler!({
        method: "resources/read",
        params: { uri: "repo://lighthouse/feature-x" },
      });

      expect(result.contents[0].uri).toBe("repo://lighthouse/feature-x");
      expect(JSON.parse(result.contents[0].text)).toEqual({ score: 100 });
    });

    it("should handle repo://playwright/:branch", async () => {
      const handler = requestHandlers.get("resources/read");
      vi.spyOn(playwrightModule, "runPlaywrightHandler").mockResolvedValue({ passed: true } as any);

      const result = await handler!({
        method: "resources/read",
        params: { uri: "repo://playwright/feature-x" },
      });

      expect(result.contents[0].uri).toBe("repo://playwright/feature-x");
      expect(JSON.parse(result.contents[0].text)).toEqual({ passed: true });
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
      });
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
