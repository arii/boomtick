import { describe, expect, it } from "vitest";
import { loadStandaloneAgentContext, readAgentContextHandler } from "./repo.read_agent_context.js";

describe("Standalone Agent Context Loader", () => {
  it("should load agent context without submodule references", () => {
    const context = loadStandaloneAgentContext(process.cwd());
    expect(context).toHaveProperty("packageName");
    expect(context).toHaveProperty("gitCommit");
    expect(context).not.toHaveProperty("submodules");
  });

  it("should handle readAgentContextHandler with default workspace", async () => {
    const res = await readAgentContextHandler({});
    expect(res.status).toBe("success");
    expect(res).toHaveProperty("packageName");
    expect(res).toHaveProperty("gitCommit");
  });

  it("readAgentContextHandler should accept optional repoPath argument", async () => {
    const res = await readAgentContextHandler({ repoPath: process.cwd() });
    expect(res).toHaveProperty("status", "success");
    expect(res).toHaveProperty("packageName");
    expect(res).toHaveProperty("gitCommit");
  });

  it("readAgentContextHandler should accept path argument", async () => {
    const res = await readAgentContextHandler({ path: process.cwd() });
    expect(res).toHaveProperty("status", "success");
    expect(res).toHaveProperty("packageName");
  });

  it("readAgentContextHandler should accept repo argument", async () => {
    const res = await readAgentContextHandler({ repo: "arii/tech-dancer" });
    expect(res).toHaveProperty("status", "success");
    expect(res).toHaveProperty("repo", "arii/tech-dancer");
  });

  it("should handle multi-repo context querying when all: true is passed", async () => {
    const res = await readAgentContextHandler({ all: true });
    expect(res.status).toBe("success");
    expect(res.ecosystem).toBe(true);
    expect(Array.isArray(res.repos)).toBe(true);
    expect(res.repos.length).toBeGreaterThan(0);
  });
});
