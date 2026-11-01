import * as fs from "fs";
import * as fsp from "fs/promises";
import * as path from "path";
import * as crypto from "crypto";
import { runCommand } from "./shell.js";
import { AgentContractConfig } from "../tools/contract.js";

const LOCKFILE_NAMES = [
  "pnpm-lock.yaml",
  "package-lock.json",
  "poetry.lock",
  "requirements.txt",
] as const;

const DEPENDENCY_DIRS = [
  "node_modules",
  ".venv",
  "venv",
] as const;

/**
 * Computes a deterministic SHA-256 hash of repository lockfiles.
 * Inspects pnpm-lock.yaml, package-lock.json, poetry.lock, requirements.txt in order.
 * If multiple lockfiles exist, hashes all found lockfile contents in sorted filename order.
 */
export async function computeLockfileHash(repoPath: string): Promise<string | null> {
  const hash = crypto.createHash("sha256");
  let foundLockfile = false;

  for (const lockfileName of LOCKFILE_NAMES) {
    const lockfilePath = path.join(repoPath, lockfileName);
    if (fs.existsSync(lockfilePath)) {
      foundLockfile = true;
      const content = await fsp.readFile(lockfilePath);
      hash.update(lockfileName);
      hash.update(content);
    }
  }

  if (!foundLockfile) {
    return null;
  }

  return hash.digest("hex");
}

/**
 * Determines the dependency cache directory for a given repo and lockfile hash.
 * Checks `<repoPath>/.dependency-cache/<hash>` first, or falls back to
 * `/tmp/boomtick-dep-cache/<repoName>/<hash>` if repoPath is read-only or outside worktrees.
 */
export function getDependencyCacheDir(repoPath: string, lockfileHash: string): string {
  const repoName = path.basename(path.resolve(repoPath)) || "repo";
  const preferredDir = path.join(repoPath, ".dependency-cache", lockfileHash);

  // If preferred dir exists or parent is writable, use preferred
  try {
    const parentDir = path.join(repoPath, ".dependency-cache");
    if (!fs.existsSync(parentDir)) {
      fs.mkdirSync(parentDir, { recursive: true });
    }
    return preferredDir;
  } catch {
    return path.join("/tmp/boomtick-dep-cache", repoName, lockfileHash);
  }
}

export interface EnsureSharedDependenciesOptions {
  repoPath: string;
  worktreePath: string;
  config: Partial<AgentContractConfig>;
  logger?: {
    info?: (msg: string) => void;
    warn?: (msg: string) => void;
    error?: (msg: string) => void;
  };
}

/**
 * Executes a shell command string using sh/bash or splitting by args.
 */
async function runSetupCommand(cmd: string, cwd: string): Promise<void> {
  const result = await runCommand("sh", ["-c", cmd], { cwd });
  if (result.exitCode !== 0) {
    throw new Error(`Setup command failed with exit code ${result.exitCode}: ${result.stderr || result.stdout}`);
  }
}

/**
 * Ensures shared dependencies are configured for a worktree according to the contract's sharedDeps strategy.
 */
export async function ensureSharedDependencies(options: EnsureSharedDependenciesOptions): Promise<void> {
  const { repoPath, worktreePath, config } = options;
  const strategy = config.sharedDeps ?? "symlink";

  if (strategy === "none") {
    return;
  }

  if (strategy === "install") {
    if (config.setupCommand) {
      await runSetupCommand(config.setupCommand, worktreePath);
    }
    return;
  }

  if (strategy === "symlink") {
    const lockHash = await computeLockfileHash(worktreePath) || await computeLockfileHash(repoPath);

    if (!lockHash) {
      // No lockfile found to cache; if setupCommand exists, run in worktree
      if (config.setupCommand) {
        await runSetupCommand(config.setupCommand, worktreePath);
      }
      return;
    }

    const cacheDir = getDependencyCacheDir(repoPath, lockHash);
    const populatedMarker = path.join(cacheDir, ".boomtick-cache-populated");
    const isCacheMiss = !fs.existsSync(populatedMarker);

    if (isCacheMiss) {
      await fsp.mkdir(cacheDir, { recursive: true });

      // Copy manifest and lockfiles into cache directory if setupCommand needs them
      for (const manifestName of [
        "package.json",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "package-lock.json",
        "requirements.txt",
        "pyproject.toml",
        "poetry.lock",
      ]) {
        const src = path.join(worktreePath, manifestName);
        const altSrc = path.join(repoPath, manifestName);
        const targetSrc = fs.existsSync(src) ? src : fs.existsSync(altSrc) ? altSrc : null;
        if (targetSrc) {
          try {
            await fsp.copyFile(targetSrc, path.join(cacheDir, manifestName));
          } catch {
            // Best effort copy
          }
        }
      }

      if (config.setupCommand) {
        await runSetupCommand(config.setupCommand, cacheDir);
      } else {
        // Run setup in cacheDir or copy existing dependencies from repoPath if present
        let copiedFromRepo = false;
        for (const depDir of DEPENDENCY_DIRS) {
          const repoDepPath = path.join(repoPath, depDir);
          if (fs.existsSync(repoDepPath)) {
            const cacheDepPath = path.join(cacheDir, depDir);
            try {
              await fsp.cp(repoDepPath, cacheDepPath, { recursive: true, dereference: false });
              copiedFromRepo = true;
            } catch {
              // Ignore copy failure
            }
          }
        }
        if (!copiedFromRepo) {
          // If neither setupCommand nor existing repo deps, try default install heuristic
          if (fs.existsSync(path.join(cacheDir, "pnpm-lock.yaml"))) {
            await runSetupCommand("pnpm install --frozen-lockfile", cacheDir);
          } else if (fs.existsSync(path.join(cacheDir, "package-lock.json"))) {
            await runSetupCommand("npm ci", cacheDir);
          }
        }
      }

      await fsp.writeFile(populatedMarker, new Date().toISOString(), "utf-8");
    }

    // Now symlink discovered dependency directories from cacheDir into worktreePath
    // Check what dependency dirs exist in cacheDir or repoPath
    const candidateDirsToLink = new Set<string>();
    for (const depDir of DEPENDENCY_DIRS) {
      if (fs.existsSync(path.join(cacheDir, depDir))) {
        candidateDirsToLink.add(depDir);
      } else if (fs.existsSync(path.join(repoPath, depDir))) {
        candidateDirsToLink.add(depDir);
      }
    }

    for (const depDir of candidateDirsToLink) {
      const sourcePath = fs.existsSync(path.join(cacheDir, depDir))
        ? path.join(cacheDir, depDir)
        : path.join(repoPath, depDir);
      const destPath = path.join(worktreePath, depDir);

      if (fs.existsSync(destPath)) {
        try {
          const stat = await fsp.lstat(destPath);
          if (stat.isSymbolicLink()) {
            await fsp.unlink(destPath);
          } else {
            // Directory exists in worktree, do not overwrite unless empty
            continue;
          }
        } catch {
          // Continue to symlink attempt
        }
      }

      try {
        await fsp.symlink(sourcePath, destPath, "junction");
      } catch (e) {
        console.warn(`Failed to symlink ${sourcePath} to ${destPath}:`, e);
      }
    }
  }
}
