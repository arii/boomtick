import { describe, expect, it } from "vitest";
import path from "path";
import fs from "fs";
import os from "os";
import { execSync } from "child_process";
import {
  RepoResolutionError,
  getVectorIndexStatus,
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

describe("getVectorIndexStatus staleness", () => {
  function makeTmpRepo(): string {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "vector-index-status-"));
    execSync(
      'git init -q -b main && git config user.email "t@example.com" && git config user.name "t" && git commit -q --allow-empty -m init',
      { cwd: dir, stdio: "pipe" },
    );
    return dir;
  }

  it("reports cold when .agent-context.json is missing", () => {
    const dir = makeTmpRepo();
    const status = getVectorIndexStatus(dir);
    expect(status.warm).toBe(false);
    expect(status.lastWarmedAt).toBeNull();
    expect(status.staleFiles).toContain(".agent-context.json missing");
  });

  it("reports warm when .agent-context.json was written after the HEAD commit (gitignored file)", () => {
    const dir = makeTmpRepo();
    fs.writeFileSync(path.join(dir, ".agent-context.json"), "{}");
    const status = getVectorIndexStatus(dir);
    expect(status.warm).toBe(true);
    expect(status.lastWarmedAt).not.toBeNull();
    expect(status.staleFiles).toEqual([]);
  });

  it("reports stale when a commit lands after the context was warmed", () => {
    const dir = makeTmpRepo();
    const contextFile = path.join(dir, ".agent-context.json");
    fs.writeFileSync(contextFile, "{}");
    // Age the context file well below the next commit's timestamp.
    const old = new Date(Date.now() - 60_000);
    fs.utimesSync(contextFile, old, old);
    execSync("git commit -q --allow-empty -m later", { cwd: dir, stdio: "pipe" });

    const status = getVectorIndexStatus(dir);
    expect(status.warm).toBe(false);
    expect(status.staleFiles.some((f) => f.includes("HEAD"))).toBe(true);
  });

  it("reports stale when a key file is newer than the context", () => {
    const dir = makeTmpRepo();
    const contextFile = path.join(dir, ".agent-context.json");
    fs.writeFileSync(contextFile, "{}");
    const old = new Date(Date.now() - 60_000);
    fs.utimesSync(contextFile, old, old);
    fs.writeFileSync(path.join(dir, "package.json"), "{}");

    const status = getVectorIndexStatus(dir);
    expect(status.warm).toBe(false);
    expect(status.staleFiles).toContain("package.json");
  });

  it("does not crash outside a git repo and falls back to file presence", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "vector-index-nogit-"));
    fs.writeFileSync(path.join(dir, ".agent-context.json"), "{}");
    const status = getVectorIndexStatus(dir);
    expect(status.warm).toBe(true);
    expect(status.lastWarmedAt).not.toBeNull();
  });
});

