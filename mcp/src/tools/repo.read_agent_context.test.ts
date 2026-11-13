import { describe, expect, it } from "vitest";
import path from "path";
import {
  RepoResolutionError,
  loadStandaloneAgentContext,
  readAgentContextHandler,
  resolveTargetRepoPath,
} from "./repo.read_agent_context.js";
import { config } from "../config.js";

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

  it("readAgentContextHandler should accept repo argument resolving via per-repo config", async () => {
    const res = await readAgentContextHandler({ repo: "arii/boomtick" });
    expect(res).toHaveProperty("status", "success");
    expect(res).toHaveProperty("repo", "arii/boomtick");
  });

  it("readAgentContextHandler should fail loudly for an unregistered repo", async () => {
    await expect(
      readAgentContextHandler({ repo: "arii/does-not-exist" })
    ).rejects.toThrow(RepoResolutionError);
  });

  it("should handle multi-repo context querying when all: true is passed", async () => {
    const res = await readAgentContextHandler({ all: true });
    expect(res.status).toBe("success");
    if (!("ecosystem" in res)) throw new Error("expected ecosystem response");
    expect(res.ecosystem).toBe(true);
    expect(Array.isArray(res.repos)).toBe(true);
    expect(res.repos.length).toBeGreaterThan(0);
  });

  it("should label the default context with the per-repo declared github_repo", async () => {
    const res = await readAgentContextHandler({});
    expect(res.status).toBe("success");
    // boomtick's own project_config.json declares github_repo: arii/boomtick,
    // so the default context must never wear an unrelated repo's label.
    expect(res).toHaveProperty("repo", "arii/boomtick");
  });
});

describe("resolveTargetRepoPath", () => {
  it("should throw RepoResolutionError for an unregistered repo instead of falling back to boomtick", async () => {
    await expect(resolveTargetRepoPath({ repo: "arii/does-not-exist" })).rejects.toThrow(
      RepoResolutionError
    );
    await expect(resolveTargetRepoPath({ repo: "does-not-exist" })).rejects.toThrow(
      /Unknown repository/
    );
  });

  it("should resolve a repo declared by the caller's own project_config.json github_repo", async () => {
    const resolved = await resolveTargetRepoPath({ repo: "boomtick" });
    expect(path.resolve(resolved)).toBe(path.resolve(config.repoPath));
  });

  it("should resolve a registered ecosystem repo by full name or basename", async () => {
    const resolved = await resolveTargetRepoPath({ repo: "arii/remote-server" });
    expect(path.basename(resolved)).toBe("remote-server");
    const resolvedByBasename = await resolveTargetRepoPath({ repo: "remote-server" });
    expect(path.resolve(resolvedByBasename)).toBe(path.resolve(resolved));
  });
});
