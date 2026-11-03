import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import fs from "fs/promises";
import os from "os";
import path from "path";
import { execSync } from "child_process";
import { config } from "../config.js";
import { worktreeCreateHandler } from "./worktree.create.js";
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
      branch: "feat/wt-test",
      baseBranch: "main",
      repo: null,
    } as any);
    expect(created.worktreeId).toMatch(/^wt-[0-9a-f]{8}$/);
    expect(created.branch).toBe("feat/wt-test");

    const listed = await worktreeListHandler({ repo: null } as any);
    expect(listed.worktrees.map((w: any) => w.worktreeId)).toContain(created.worktreeId);

    const removed = await worktreeRemoveHandler({
      worktreeId: created.worktreeId,
      force: false,
      repo: null,
    } as any);
    expect(removed.removed).toBe(true);

    const listedAfter = await worktreeListHandler({ repo: null } as any);
    expect(listedAfter.worktrees.map((w: any) => w.worktreeId)).not.toContain(created.worktreeId);
  });

  it("remove refuses dirty trees without force", async () => {
    const created = await worktreeCreateHandler({
      branch: "feat/wt-dirty",
      baseBranch: "main",
      repo: null,
    } as any);
    await fs.writeFile(path.join(created.path, "dirty.txt"), "x\n");
    await expect(
      worktreeRemoveHandler({ worktreeId: created.worktreeId, force: false, repo: null } as any)
    ).rejects.toThrow(/uncommitted changes/);
    const removed = await worktreeRemoveHandler({
      worktreeId: created.worktreeId,
      force: true,
      repo: null,
    } as any);
    expect(removed.removed).toBe(true);
  });

  it("remove rejects bad ids and missing worktrees", async () => {
    await expect(
      worktreeRemoveHandler({ worktreeId: "../escape", force: true, repo: null } as any)
    ).rejects.toThrow(/Invalid worktree id/);
    await expect(
      worktreeRemoveHandler({ worktreeId: "wt-deadbeef", force: true, repo: null } as any)
    ).rejects.toThrow(/not found/);
  });
});
