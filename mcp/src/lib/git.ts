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
