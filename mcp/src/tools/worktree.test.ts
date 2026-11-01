import { describe, it, expect, beforeEach, afterEach } from "vitest";
import path from "path";
import fs from "fs/promises";
import * as syncFs from "fs";
import { worktreeCreateHandler } from "./worktree.create.js";
import { worktreeListHandler } from "./worktree.list.js";
import { worktreeRemoveHandler } from "./worktree.remove.js";
import { runCommand } from "../lib/shell.js";
import { sweepStaleWorktrees, getContractWorktreeTtl } from "../lib/git.js";

const TEST_REPO = path.join("/tmp", `test-worktree-repo-${Date.now()}`);

describe("Worktree Lifecycle Tools", () => {
  beforeEach(async () => {
    // Initialize a temporary git repository for testing
    await fs.mkdir(TEST_REPO, { recursive: true });
    await runCommand("git", ["init", "-b", "main"], { cwd: TEST_REPO });
    await runCommand("git", ["config", "user.name", "Test Agent"], { cwd: TEST_REPO });
    await runCommand("git", ["config", "user.email", "agent@boomtick.test"], { cwd: TEST_REPO });
    await fs.writeFile(path.join(TEST_REPO, "README.md"), "# Test Repo\n");
    await runCommand("git", ["add", "."], { cwd: TEST_REPO });
    await runCommand("git", ["commit", "-m", "Initial commit"], { cwd: TEST_REPO });
  });

  afterEach(async () => {
    try {
      await fs.rm(TEST_REPO, { recursive: true, force: true });
    } catch {
      // Ignore cleanup error
    }
  });

  describe("worktree_create", () => {
    it("should throw error if writeMode is false", async () => {
      await expect(
        worktreeCreateHandler({
          path: TEST_REPO,
          name: "test-feature",
          writeMode: false,
          baseBranch: "main",
          sparsePaths: null,
          repo: null,
        })
      ).rejects.toThrow("writeMode must be true");
    });

    it("should create worktree with sanitized name, branch, and directory", async () => {
      const res = await worktreeCreateHandler({
        path: TEST_REPO,
        name: "Feature-Test_123!",
        writeMode: true,
        baseBranch: "main",
        sparsePaths: null,
        repo: null,
      });

      expect(res.worktreeId).toMatch(/^wt-feature-test-123-\d+$/);
      expect(res.branch).toMatch(/^agent\/feature-test-123-\d+$/);
      expect(res.baseBranch).toBe("main");
      expect(res.createdAt).toBeGreaterThan(0);
      expect(syncFs.existsSync(res.path)).toBe(true);

      // Verify git branch exists
      const branchRes = await runCommand("git", ["branch", "--list", res.branch], { cwd: TEST_REPO });
      expect(branchRes.stdout).toContain(res.branch);
    });

    it("should support sparse checkout when sparsePaths are provided", async () => {
      // Add nested files in main repo
      await fs.mkdir(path.join(TEST_REPO, "src/components"), { recursive: true });
      await fs.mkdir(path.join(TEST_REPO, "docs"), { recursive: true });
      await fs.writeFile(path.join(TEST_REPO, "src/components/Button.tsx"), "export const Button = () => null;");
      await fs.writeFile(path.join(TEST_REPO, "docs/index.md"), "# Documentation");
      await runCommand("git", ["add", "."], { cwd: TEST_REPO });
      await runCommand("git", ["commit", "-m", "Add directories"], { cwd: TEST_REPO });

      const res = await worktreeCreateHandler({
        path: TEST_REPO,
        name: "sparse-feature",
        writeMode: true,
        baseBranch: "main",
        sparsePaths: ["src/components"],
        repo: null,
      });

      expect(syncFs.existsSync(res.path)).toBe(true);
      expect(syncFs.existsSync(path.join(res.path, "src/components/Button.tsx"))).toBe(true);
      // docs should not exist due to sparse checkout
      expect(syncFs.existsSync(path.join(res.path, "docs/index.md"))).toBe(false);
    });
  });

  describe("worktree_list", () => {
    it("should list active managed worktrees with disk usage and changed files", async () => {
      const created = await worktreeCreateHandler({
        path: TEST_REPO,
        name: "list-test",
        writeMode: true,
        baseBranch: "main",
        sparsePaths: null,
        repo: null,
      });

      // Add an uncommitted modification in the worktree
      await fs.writeFile(path.join(created.path, "new_file.txt"), "hello world");

      const listRes = await worktreeListHandler({ path: TEST_REPO });
      expect(listRes.worktrees.length).toBeGreaterThanOrEqual(1);

      const target = listRes.worktrees.find((w) => w.worktreeId === created.worktreeId);
      expect(target).toBeDefined();
      expect(target?.branch).toBe(created.branch);
      expect(target?.changedFilesCount).toBe(1);
      expect(target?.diskUsageBytes).toBeGreaterThan(0);
      expect(target?.ageSeconds).toBeGreaterThanOrEqual(0);
    });
  });

  describe("worktree_remove", () => {
    it("should throw error if writeMode is false", async () => {
      await expect(
        worktreeRemoveHandler({
          worktreeId: "wt-dummy",
          path: TEST_REPO,
          force: false,
          writeMode: false,
          repo: null,
        })
      ).rejects.toThrow("writeMode must be true");
    });

    it("should refuse removal when worktree has uncommitted modifications without force", async () => {
      const created = await worktreeCreateHandler({
        path: TEST_REPO,
        name: "dirty-wt",
        writeMode: true,
        baseBranch: "main",
        sparsePaths: null,
        repo: null,
      });

      // Dirty the worktree
      await fs.writeFile(path.join(created.path, "dirty.txt"), "modified");

      await expect(
        worktreeRemoveHandler({
          worktreeId: created.worktreeId,
          path: TEST_REPO,
          force: false,
          writeMode: true,
          repo: null,
        })
      ).rejects.toThrow("uncommitted modified files");

      // Verify worktree still exists
      expect(syncFs.existsSync(created.path)).toBe(true);
    });

    it("should remove dirty worktree when force: true", async () => {
      const created = await worktreeCreateHandler({
        path: TEST_REPO,
        name: "force-wt",
        writeMode: true,
        baseBranch: "main",
        sparsePaths: null,
        repo: null,
      });

      await fs.writeFile(path.join(created.path, "dirty.txt"), "modified");

      const res = await worktreeRemoveHandler({
        worktreeId: created.worktreeId,
        path: TEST_REPO,
        force: true,
        writeMode: true,
        repo: null,
      });

      expect(res.status).toBe("removed");
      expect(res.worktreeId).toBe(created.worktreeId);
      expect(res.freedBytes).toBeGreaterThan(0);
      expect(syncFs.existsSync(created.path)).toBe(false);
    });

    it("should cleanly remove clean worktree without force", async () => {
      const created = await worktreeCreateHandler({
        path: TEST_REPO,
        name: "clean-wt",
        writeMode: true,
        baseBranch: "main",
        sparsePaths: null,
        repo: null,
      });

      const res = await worktreeRemoveHandler({
        worktreeId: created.worktreeId,
        path: TEST_REPO,
        force: false,
        writeMode: true,
        repo: null,
      });

      expect(res.status).toBe("removed");
      expect(res.worktreeId).toBe(created.worktreeId);
      expect(syncFs.existsSync(created.path)).toBe(false);
    });
  });

  describe("TTL sweep and contract configuration", () => {
    it("should read worktree TTL from AGENT_CONTRACT.md if defined", async () => {
      const agentsDir = path.join(TEST_REPO, ".agents");
      await fs.mkdir(agentsDir, { recursive: true });
      await fs.writeFile(path.join(agentsDir, "AGENT_CONTRACT.md"), "# Contract\nworktree_ttl_seconds: 3600\n");

      const ttl = await getContractWorktreeTtl(TEST_REPO);
      expect(ttl).toBe(3600);
    });

    it("should prune worktrees older than TTL", async () => {
      const created = await worktreeCreateHandler({
        path: TEST_REPO,
        name: "stale-wt",
        writeMode: true,
        baseBranch: "main",
        sparsePaths: null,
        repo: null,
      });

      expect(syncFs.existsSync(created.path)).toBe(true);

      // Sweep with TTL = 0 seconds (should prune all created worktrees)
      const sweepRes = await sweepStaleWorktrees(TEST_REPO, 0);

      expect(sweepRes.sweptWorktreeIds).toContain(created.worktreeId);
      expect(sweepRes.totalFreedBytes).toBeGreaterThan(0);
      expect(syncFs.existsSync(created.path)).toBe(false);
    });
  });
});
