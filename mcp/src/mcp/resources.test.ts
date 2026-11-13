import { describe, it, expect, vi, beforeEach } from "vitest";
import { BoomtickMCPServer } from "./server.js";
import { MCP_RESOURCES, MCP_RESOURCE_TEMPLATES } from "./definitions.js";
import fs from "fs/promises";
import * as gitLibModule from "../lib/git.js";
import * as tdCliModule from "../lib/tdCli.js";
import * as gitPrModule from "../tools/github.pr.js";

vi.mock("fs/promises");
vi.mock("../config.js", () => ({
  config: {
    repoPath: "/mock/repo",
  },
}));
vi.mock("../lib/git.js", () => ({ getChangedFiles: vi.fn() }));
vi.mock("../lib/tdCli.js", () => ({ runTDCli: vi.fn() }));
vi.mock("../tools/github.pr.js", () => ({ githubPrHandler: vi.fn() }));

type TestContent = { uri: string; mimeType: string; text: string };

type TestResult = {
  resources: Array<{ uri: string }>;
  resourceTemplates: Array<{ uriTemplate: string }>;
  contents: TestContent[];
};

type TestHandler = (request: {
  method: string;
  params?: Record<string, unknown>;
}) => Promise<TestResult>;

type TestServerInstance = {
  _requestHandlers?: Map<string, TestHandler>;
  requestHandlers?: Map<string, TestHandler>;
};

describe("MCP resource handlers (URI consistency)", () => {
  let readHandler: TestHandler;
  let listHandler: TestHandler;
  let templatesHandler: TestHandler;

  beforeEach(() => {
    vi.resetAllMocks();

    const mcpServer = new BoomtickMCPServer();
    const serverInstance = (mcpServer as unknown as { server: TestServerInstance }).server;
    const handlers = serverInstance._requestHandlers || serverInstance.requestHandlers;
    expect(handlers).toBeDefined();

    readHandler = handlers!.get("resources/read")!;
    listHandler = handlers!.get("resources/list")!;
    templatesHandler = handlers!.get("resources/templates/list")!;
    expect(readHandler).toBeDefined();

    vi.mocked(fs.readFile).mockResolvedValue("mock-file-content");
    vi.mocked(gitLibModule.getChangedFiles).mockResolvedValue([{ status: "M", path: "src/a.ts" }]);
    vi.mocked(tdCliModule.runTDCli).mockResolvedValue({ runs: [] });
    vi.mocked(gitPrModule.githubPrHandler).mockResolvedValue({
      diff: { diffText: "mock-diff" },
      ciLogs: { logs: "mock-logs" },
    } as never);
  });

  const read = (uri: string) => readHandler({ method: "resources/read", params: { uri } });

  it("resolves every advertised resource URI — listing never 404s", async () => {
    for (const resource of MCP_RESOURCES) {
      const result = await read(resource.uri);
      expect(result.contents, `resource ${resource.uri}`).toHaveLength(1);
      expect(result.contents[0].uri, `resource ${resource.uri}`).toBe(resource.uri);
    }
  });

  it("resolves every advertised resource template with a sample parameter", async () => {
    for (const template of MCP_RESOURCE_TEMPLATES) {
      const sample = template.uriTemplate.replace("{prNumber}", "12").replace("{branch}", "main");
      const result = await read(sample);
      expect(result.contents, `template ${template.uriTemplate}`).toHaveLength(1);
      expect(result.contents[0].uri, `template ${template.uriTemplate}`).toBe(sample);
    }
  });

  it("does not advertise repo://repair-report/{branch} — it has no read handler (audit H5)", async () => {
    const listed = await listHandler({ method: "resources/list" });
    const templates = await templatesHandler({ method: "resources/templates/list" });

    const allUris = [...listed.resources.map((r) => r.uri), ...templates.resourceTemplates.map((t) => t.uriTemplate)];
    expect(allUris.some((uri) => uri.startsWith("repo://repair-report"))).toBe(false);
    await expect(read("repo://repair-report/main")).rejects.toThrow(/Resource not found/);
  });

  it("keeps the legacy repo://agent-contract URI retired (boomtick#1012)", async () => {
    const listed = await listHandler({ method: "resources/list" });
    expect(listed.resources.map((r) => r.uri)).not.toContain("repo://agent-contract");
    await expect(read("repo://agent-contract")).rejects.toThrow(/Resource not found/);
  });

  it("serves the canonical agent-contract resource under both advertised schemes", async () => {
    for (const uri of ["boomtick://workspace/agent-contract", "mcp://workspace/agent-contract"]) {
      const result = await read(uri);
      expect(result.contents[0]).toMatchObject({ uri, mimeType: "text/markdown", text: "mock-file-content" });
    }
  });

  it("returns changed files for the changed-files resource", async () => {
    const result = await read("mcp://git/changed-files");
    expect(JSON.parse(result.contents[0].text)).toEqual({ files: [{ status: "M", path: "src/a.ts" }] });
  });
});
