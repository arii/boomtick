import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import fs from "fs/promises";
import os from "os";
import path from "path";
import { execSync } from "child_process";
import { config } from "../config.js";
import { worktreeCreateHandler, sanitizeBranchName } from "./worktree.create.js";
import { worktreeListHandler } from "./worktree.list.js";
import { worktreeRemoveHandler } from "./worktree.remove.js";

describe("worktree lifecycle tools", () => {
  let tmpRepoDir: string;

  beforeEach(async () => {
    tmpRepoDir = await fs.mkdtemp(path.join(os.tmpdir(), "bt-wt-"));
    execSync("git init -b main", { cwd: tmpRepoDir });
    execSync('git config user.email "test@example.com"', { cwd: tmpRepoDir });
    execSync('git config user.name "Test Runner"', { cwd: tmpRepoDir });
    await fs.writeFile(path.join(tmpRepoDir, "README.md"), "# test\n");
    execSync("git add README.md && git commit -m init", { cwd: tmpRepoDir });
    vi.spyOn(config, "repoPath", "get").mockReturnValue(tmpRepoDir);
  });

  afterEach(async () => {
    vi.restoreAllMocks();
    try {
      await fs.rm(tmpRepoDir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  });

  it("create -> list -> remove round trip", async () => {
    const created = await worktreeCreateHandler({
      name: "Wt Test",
      baseBranch: "main",
      writeMode: true,
      repo: null,
      path: null,
    } as any);
    expect(created.worktreeId).toMatch(/^wt-[0-9a-f]{8}$/);
    expect(created.branch).toBe("wt-test");
    expect(created.baseBranch).toBe("main");
    expect(created.createdAt).toBeGreaterThan(0);

    const listed = await worktreeListHandler({ repo: null, path: null } as any);
    const ids = listed.worktrees.map((w: any) => w.worktreeId);
    expect(ids).toContain(created.worktreeId);
    const item = listed.worktrees.find((w: any) => w.worktreeId === created.worktreeId);
    expect(item).toBeDefined();
    expect(item!.branch).toBe("wt-test");
    expect(item!.ageSeconds).toBeGreaterThanOrEqual(0);
    expect(item!.changedFilesCount).toBe(0);
    expect(item!.diskUsageBytes).toBeGreaterThan(0);

    const removed = await worktreeRemoveHandler({
      worktreeId: created.worktreeId,
      force: false,
      writeMode: true,
      repo: null,
      path: null,
    } as any);
    expect(removed.status).toBe("removed");
    expect(removed.freedBytes).toBeGreaterThan(0);

    const listedAfter = await worktreeListHandler({ repo: null, path: null } as any);
    expect(listedAfter.worktrees.map((w: any) => w.worktreeId)).not.toContain(created.worktreeId);
  });

  it("create requires writeMode and generates a branch without name", async () => {
    await expect(
      worktreeCreateHandler({ name: "x", writeMode: false } as any)
    ).rejects.toThrow(/writeMode must be true/);
    const created = await worktreeCreateHandler({ writeMode: true } as any);
    expect(created.branch).toMatch(/^wt-[0-9a-f]{8}$/);
    await worktreeRemoveHandler({
      worktreeId: created.worktreeId,
      force: true,
      writeMode: true,
    } as any);
  });

  it("remove refuses dirty trees without force", async () => {
    const created = await worktreeCreateHandler({ writeMode: true } as any);
    await fs.writeFile(path.join(created.path, "dirty.txt"), "x\n");
    await expect(
      worktreeRemoveHandler({ worktreeId: created.worktreeId, force: false, writeMode: true } as any)
    ).rejects.toThrow(/uncommitted changes/);
    const removed = await worktreeRemoveHandler({
      worktreeId: created.worktreeId,
      force: true,
      writeMode: true,
    } as any);
    expect(removed.status).toBe("removed");
  });

  it("remove rejects bad ids, missing worktrees, and missing writeMode", async () => {
    await expect(
      worktreeRemoveHandler({ worktreeId: "../escape", force: true, writeMode: true } as any)
    ).rejects.toThrow(/Invalid worktree id/);
    await expect(
      worktreeRemoveHandler({ worktreeId: "wt-deadbeef", force: true, writeMode: true } as any)
    ).rejects.toThrow(/not found/);
    await expect(
      worktreeRemoveHandler({ worktreeId: "wt-deadbeef", force: true, writeMode: false } as any)
    ).rejects.toThrow(/writeMode must be true/);
  });

  it("sanitizes branch slugs", () => {
    expect(sanitizeBranchName("Fix That_Thing 2!")).toBe("fix-that-thing-2");
    expect(sanitizeBranchName("---")).toBe("");
  });
});
