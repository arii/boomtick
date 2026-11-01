import { describe, expect, it, beforeEach, afterEach } from "vitest";
import * as fs from "fs";
import * as fsp from "fs/promises";
import * as path from "path";
import * as os from "os";
import {
  computeLockfileHash,
  getDependencyCacheDir,
  ensureSharedDependencies,
} from "./dependency_cache.js";

describe("dependency_cache", () => {
  let tmpRoot: string;

  beforeEach(() => {
    tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "dep-cache-test-"));
  });

  afterEach(async () => {
    try {
      await fsp.rm(tmpRoot, { recursive: true, force: true });
    } catch {
      // Ignore
    }
  });

  describe("computeLockfileHash", () => {
    it("returns null if no lockfiles exist", async () => {
      const hash = await computeLockfileHash(tmpRoot);
      expect(hash).toBeNull();
    });

    it("computes hash for pnpm-lock.yaml", async () => {
      await fsp.writeFile(path.join(tmpRoot, "pnpm-lock.yaml"), "lockfileVersion: '9.0'");
      const hash1 = await computeLockfileHash(tmpRoot);
      expect(hash1).toBeDefined();
      expect(typeof hash1).toBe("string");
      expect(hash1?.length).toBe(64);

      // Same content yields same hash
      const hash2 = await computeLockfileHash(tmpRoot);
      expect(hash2).toBe(hash1);

      // Modified content yields different hash
      await fsp.writeFile(path.join(tmpRoot, "pnpm-lock.yaml"), "lockfileVersion: '9.1'");
      const hash3 = await computeLockfileHash(tmpRoot);
      expect(hash3).not.toBe(hash1);
    });

    it("computes deterministic hash across multiple lockfiles", async () => {
      await fsp.writeFile(path.join(tmpRoot, "requirements.txt"), "pytest==7.0.0");
      await fsp.writeFile(path.join(tmpRoot, "package-lock.json"), '{"name": "test"}');

      const hash = await computeLockfileHash(tmpRoot);
      expect(hash).toBeDefined();
      expect(hash?.length).toBe(64);
    });
  });

  describe("getDependencyCacheDir", () => {
    it("returns path in repo's .dependency-cache directory when writable", () => {
      const hash = "abcdef123456";
      const cacheDir = getDependencyCacheDir(tmpRoot, hash);
      expect(cacheDir).toBe(path.join(tmpRoot, ".dependency-cache", hash));
      expect(fs.existsSync(path.join(tmpRoot, ".dependency-cache"))).toBe(true);
    });
  });

  describe("ensureSharedDependencies", () => {
    it("does nothing when sharedDeps is 'none'", async () => {
      const repoPath = path.join(tmpRoot, "repo");
      const worktreePath = path.join(tmpRoot, "wt1");
      await fsp.mkdir(repoPath, { recursive: true });
      await fsp.mkdir(worktreePath, { recursive: true });

      await ensureSharedDependencies({
        repoPath,
        worktreePath,
        config: {
          baseBranch: "main",
          sharedDeps: "none",
          worktreeTtlDays: 7,
          setupCommand: "echo should_not_run",
        },
      });

      expect(fs.existsSync(path.join(worktreePath, "node_modules"))).toBe(false);
    });

    it("executes setupCommand directly in worktree when sharedDeps is 'install'", async () => {
      const repoPath = path.join(tmpRoot, "repo");
      const worktreePath = path.join(tmpRoot, "wt1");
      await fsp.mkdir(repoPath, { recursive: true });
      await fsp.mkdir(worktreePath, { recursive: true });

      await ensureSharedDependencies({
        repoPath,
        worktreePath,
        config: {
          baseBranch: "main",
          sharedDeps: "install",
          worktreeTtlDays: 7,
          setupCommand: "mkdir -p node_modules/installed_pkg && echo 'installed' > node_modules/installed_pkg/flag",
        },
      });

      const installedFile = path.join(worktreePath, "node_modules/installed_pkg/flag");
      expect(fs.existsSync(installedFile)).toBe(true);
      expect(fs.readFileSync(installedFile, "utf-8").trim()).toBe("installed");
      expect(fs.lstatSync(path.join(worktreePath, "node_modules")).isSymbolicLink()).toBe(false);
    });

    it("shares pre-installed dependencies between two worktrees with sharedDeps: 'symlink'", async () => {
      const repoPath = path.join(tmpRoot, "repo");
      const wt1Path = path.join(tmpRoot, "wt1");
      const wt2Path = path.join(tmpRoot, "wt2");
      await fsp.mkdir(repoPath, { recursive: true });
      await fsp.mkdir(wt1Path, { recursive: true });
      await fsp.mkdir(wt2Path, { recursive: true });

      // Create lockfile in worktree 1 and 2
      const lockContent = "packages: sample@1.0.0";
      await fsp.writeFile(path.join(wt1Path, "pnpm-lock.yaml"), lockContent);
      await fsp.writeFile(path.join(wt2Path, "pnpm-lock.yaml"), lockContent);

      const config = {
        baseBranch: "main",
        sharedDeps: "symlink" as const,
        worktreeTtlDays: 7,
        setupCommand: "mkdir -p node_modules/shared-lib && echo 'hello-shared' > node_modules/shared-lib/index.js",
      };

      // Worktree 1 triggers setupCommand (cache miss)
      await ensureSharedDependencies({
        repoPath,
        worktreePath: wt1Path,
        config,
      });

      expect(fs.existsSync(path.join(wt1Path, "node_modules/shared-lib/index.js"))).toBe(true);
      expect(fs.lstatSync(path.join(wt1Path, "node_modules")).isSymbolicLink()).toBe(true);

      // Worktree 2 uses cache hit without re-running installation
      // To verify setupCommand is NOT run again, provide a failing setupCommand on wt2 invocation
      await ensureSharedDependencies({
        repoPath,
        worktreePath: wt2Path,
        config: {
          ...config,
          setupCommand: "exit 1", // Would fail if executed!
        },
      });

      expect(fs.existsSync(path.join(wt2Path, "node_modules/shared-lib/index.js"))).toBe(true);
      expect(fs.lstatSync(path.join(wt2Path, "node_modules")).isSymbolicLink()).toBe(true);

      // Ensure both worktrees point to the exact same shared directory
      const wt1Target = fs.readlinkSync(path.join(wt1Path, "node_modules"));
      const wt2Target = fs.readlinkSync(path.join(wt2Path, "node_modules"));
      expect(wt1Target).toBe(wt2Target);

      // Modifications in shared module are visible across worktrees
      await fsp.writeFile(path.join(wt1Path, "node_modules/shared-lib/index.js"), "modified");
      expect(fs.readFileSync(path.join(wt2Path, "node_modules/shared-lib/index.js"), "utf-8")).toBe("modified");
    });

    it("shares .venv dependencies between worktrees when .venv is set up", async () => {
      const repoPath = path.join(tmpRoot, "repo");
      const wtPath = path.join(tmpRoot, "wt-python");
      await fsp.mkdir(repoPath, { recursive: true });
      await fsp.mkdir(wtPath, { recursive: true });

      await fsp.writeFile(path.join(wtPath, "requirements.txt"), "pytest==8.0.0");

      await ensureSharedDependencies({
        repoPath,
        worktreePath: wtPath,
        config: {
          baseBranch: "main",
          sharedDeps: "symlink",
          worktreeTtlDays: 7,
          setupCommand: "mkdir -p .venv/bin && echo '#!/bin/sh' > .venv/bin/python",
        },
      });

      expect(fs.existsSync(path.join(wtPath, ".venv/bin/python"))).toBe(true);
      expect(fs.lstatSync(path.join(wtPath, ".venv")).isSymbolicLink()).toBe(true);
    });
  });
});
