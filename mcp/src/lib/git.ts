import { runCommand } from "./shell.js";
import { config } from "../config.js";
import path from "path";
import fs from "fs/promises";
import { execSync } from "child_process";

const repoCache = new Map<string, string>();

export function resolveRepo(explicitRepo?: string | null, cwd?: string): string {
  if (explicitRepo && explicitRepo.trim().length > 0) {
    return explicitRepo.trim();
  }

  const targetCwd = cwd || process.cwd();
  if (repoCache.has(targetCwd)) {
    return repoCache.get(targetCwd)!;
  }

  try {
    const url = execSync("git remote get-url origin", {
      cwd: targetCwd,
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();

    const match = url.match(/[:/]([^/]+\/[^/.]+)(\.git)?$/);
    if (match) {
      repoCache.set(targetCwd, match[1]);
      return match[1];
    }
  } catch (e) {
    // Ignore error and fall back to static config
  }

  const fallback = `${config.githubOwner}/${config.githubRepo}`;
  repoCache.set(targetCwd, fallback);
  return fallback;
}

function validatePrNumber(value: unknown): number {
  const prNumber = Number(value);

  if (!Number.isInteger(prNumber) || prNumber <= 0) {
    throw new Error("Invalid PR number");
  }

  return prNumber;
}

export async function createWorktree(branch: string, prNumber: number): Promise<string> {
  const safePrNumber = validatePrNumber(prNumber);

  const workspaceRoot = "/tmp/boomtick-worktrees";
  // nosemgrep
  const worktreePath = path.join(workspaceRoot, `boomtick-mcp-rescue-${safePrNumber}`);

  // Clean up if exists
  try {
    await fs.rm(worktreePath, { recursive: true, force: true });
    await runCommand("git", ["worktree", "prune"]);
  } catch (e) { /* ignore if no previous worktree */ }

  const result = await runCommand("git", ["worktree", "add", "-b", `repair-pr-${prNumber}-${Date.now()}`, worktreePath, branch]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to create worktree: ${result.stderr}`);
  }

  return worktreePath;
}

export async function removeWorktree(worktreePath: string): Promise<void> {
  await runCommand("git", ["worktree", "remove", "--force", worktreePath]);
  await runCommand("git", ["worktree", "prune"]);
}

export interface ChangedFile {
  status: string;
  path: string;
  oldPath?: string;
}

export async function getChangedFiles(
  base: string = "main",
  head: string = "HEAD",
  cwd?: string
): Promise<ChangedFile[]> {
  const result = await runCommand(
    "git",
    ["diff", "--name-status", "-z", `${base}...${head}`],
    { cwd }
  );

  if (result.exitCode !== 0) {
    throw new Error(`Failed to get changed files: ${result.stderr}`);
  }

  const tokens = result.stdout.split("\0").filter((t) => t.length > 0);
  const files: ChangedFile[] = [];

  let i = 0;
  while (i < tokens.length) {
    const status = tokens[i];
    if (status.startsWith("R") || status.startsWith("C")) {
      const oldPath = tokens[i + 1];
      const newPath = tokens[i + 2];
      if (oldPath && newPath) {
        files.push({ status, path: newPath, oldPath });
      }
      i += 3;
    } else {
      const filePath = tokens[i + 1];
      if (filePath) {
        files.push({ status, path: filePath });
      }
      i += 2;
    }
  }

  return files;
}

export async function getMergeConflictFiles(
  baseBranch: string = "main",
  headRef: string = "HEAD",
  cwd?: string
): Promise<string[]> {
  const result = await runCommand(
    "git",
    ["merge-tree", "--write-tree", "--name-only", baseBranch, headRef],
    { cwd }
  );

  // git merge-tree returns exit code 1 if conflicts are present, 0 if clean merge
  if (result.exitCode !== 0 && result.exitCode !== 1) {
    throw new Error(`Git merge-tree failed: ${result.stderr}`);
  }

  const lines = result.stdout
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  // First line is tree hash if successful or conflict output
  // When conflicts exist, git merge-tree --write-tree --name-only outputs conflicted filenames
  // Skip tree hash line if present (40 hex chars)
  const files = lines.filter((line) => !/^[0-9a-f]{40}$/i.test(line));

  return files;
}
