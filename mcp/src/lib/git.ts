import { runCommand } from "./shell.js";
import { config } from "../config.js";
import path from "path";
import fs from "fs/promises";
import * as syncFs from "fs";
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

export interface RepoPathOptions {
  path?: string | null;
  repoPath?: string | null;
  repo?: string | null;
  cwd?: string | null;
}

export function resolveRepoPath(options: RepoPathOptions = {}): string {
  // 1. Explicit path parameter has highest precedence
  if (options.path && options.path.trim().length > 0) {
    return path.resolve(options.path.trim());
  }

  // 2. repoPath alias parameter
  if (options.repoPath && options.repoPath.trim().length > 0) {
    return path.resolve(options.repoPath.trim());
  }

  // 3. Repository name override (e.g. "arii/tech-dancer" or "tech-dancer")
  if (options.repo && options.repo.trim().length > 0) {
    const rawRepo = options.repo.trim();
    const repoName = rawRepo.includes("/") ? rawRepo.split("/")[1] : rawRepo;

    // First check project_config.json ecosystem_repos if available
    let rootPath: string = process.cwd();
    try {
      if (options.cwd && options.cwd.trim().length > 0) {
        rootPath = options.cwd.trim();
      } else if (config.repoPath) {
        rootPath = config.repoPath;
      }
    } catch {
      rootPath = process.cwd();
    }

    const projectConfigPath = path.join(rootPath, "project_config.json");
    if (syncFs.existsSync(projectConfigPath)) {
      try {
        const parsed = JSON.parse(syncFs.readFileSync(projectConfigPath, "utf-8"));
        if (parsed?.ecosystem_repos && typeof parsed.ecosystem_repos === "object") {
          for (const [key, relPath] of Object.entries(parsed.ecosystem_repos)) {
            const keyRepoName = key.includes("/") ? key.split("/")[1] : key;
            if (key === rawRepo || keyRepoName === repoName) {
              return path.resolve(rootPath, relPath as string);
            }
          }
        }
      } catch {
        // Fallback to directory inspection
      }
    }

    // Check sibling directory relative to cwd or rootPath
    const candidateDirs = [
      path.resolve(process.cwd(), "..", repoName),
      path.resolve(rootPath, "..", repoName),
    ];
    for (const cand of candidateDirs) {
      if (syncFs.existsSync(cand)) {
        return cand;
      }
    }
  }

  // 4. Explicit cwd parameter
  if (options.cwd && options.cwd.trim().length > 0) {
    return path.resolve(options.cwd.trim());
  }

  // 5. Configured repoPath or process.cwd()
  try {
    if (config.repoPath && syncFs.existsSync(config.repoPath)) {
      return config.repoPath;
    }
  } catch {
    // Fall back to process.cwd()
  }

  return process.cwd();
}

function validatePrNumber(value: unknown): number {
  const prNumber = Number(value);

  if (!Number.isInteger(prNumber) || prNumber <= 0) {
    throw new Error("Invalid PR number");
  }

  return prNumber;
}

export async function createWorktree(branch: string, prNumber: number, baseRepoPath?: string): Promise<string> {
  const safePrNumber = validatePrNumber(prNumber);

  const workspaceRoot = "/tmp/boomtick-worktrees";
  // nosemgrep
  const worktreePath = path.join(workspaceRoot, `boomtick-mcp-rescue-${safePrNumber}`);
  const cwdOption = baseRepoPath ? { cwd: baseRepoPath } : undefined;

  // Clean up if exists
  try {
    await fs.rm(worktreePath, { recursive: true, force: true });
    await runCommand("git", ["worktree", "prune"], cwdOption);
  } catch (e) { /* ignore if no previous worktree */ }

  const result = await runCommand(
    "git",
    ["worktree", "add", "-b", `repair-pr-${prNumber}-${Date.now()}`, worktreePath, branch],
    cwdOption
  );

  if (result.exitCode !== 0) {
    throw new Error(`Failed to create worktree: ${result.stderr}`);
  }

  return worktreePath;
}

export async function removeWorktree(worktreePath: string, baseRepoPath?: string): Promise<void> {
  const cwdOption = baseRepoPath ? { cwd: baseRepoPath } : undefined;
  await runCommand("git", ["worktree", "remove", "--force", worktreePath], cwdOption);
  await runCommand("git", ["worktree", "prune"], cwdOption);
}

export async function getDirectorySize(dirPath: string): Promise<number> {
  try {
    let totalSize = 0;
    const entries = await fs.readdir(dirPath, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dirPath, entry.name);
      try {
        const stats = await fs.lstat(fullPath);
        if (stats.isDirectory()) {
          totalSize += await getDirectorySize(fullPath);
        } else {
          totalSize += stats.size;
        }
      } catch {
        // Skip inaccessible entries
      }
    }
    return totalSize;
  } catch {
    return 0;
  }
}

export interface CreateManagedWorktreeOptions {
  targetRepoPath: string;
  name?: string | null;
  baseBranch?: string | null;
  sparsePaths?: string[] | null;
}

export interface ManagedWorktreeResult {
  worktreeId: string;
  path: string;
  branch: string;
  baseBranch: string;
  createdAt: number;
}

export async function createManagedWorktree(options: CreateManagedWorktreeOptions): Promise<ManagedWorktreeResult> {
  const targetRepo = options.targetRepoPath;
  const rawName = (options.name || "agent").toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/^-+|-+$/g, "") || "agent";
  const now = Date.now();
  const worktreeId = `wt-${rawName}-${now}`;
  const branch = `agent/${rawName}-${now}`;

  // Base branch resolution: explicit -> dynamic config defaultBaseBranch -> main
  let baseBranch: string = options.baseBranch?.trim() || "";
  if (!baseBranch) {
    try {
      baseBranch = config.defaultBaseBranch || "main";
    } catch {
      baseBranch = "main";
    }
  }

  // Worktree directory resolution:
  // Primary: <repo>/.worktrees/<worktreeId>
  // Fallback: /tmp/boomtick-worktrees/<worktreeId>
  let worktreePath: string = path.join(targetRepo, ".worktrees", worktreeId);
  try {
    const parentDir = path.join(targetRepo, ".worktrees");
    await fs.mkdir(parentDir, { recursive: true });
  } catch {
    const fallbackDir = "/tmp/boomtick-worktrees";
    await fs.mkdir(fallbackDir, { recursive: true });
    worktreePath = path.join(fallbackDir, worktreeId);
  }

  // Ensure baseBranch ref is available (try origin/baseBranch or baseBranch)
  try {
    await runCommand("git", ["fetch", "origin", baseBranch], { cwd: targetRepo });
  } catch {
    // Ignore fetch failure if local branch or offline
  }

  let startPoint = `origin/${baseBranch}`;
  const verifyOrigin = await runCommand("git", ["rev-parse", "--verify", startPoint], { cwd: targetRepo });
  if (verifyOrigin.exitCode !== 0) {
    const verifyLocal = await runCommand("git", ["rev-parse", "--verify", baseBranch], { cwd: targetRepo });
    if (verifyLocal.exitCode === 0) {
      startPoint = baseBranch;
    } else {
      // Fallback: HEAD
      startPoint = "HEAD";
    }
  }

  const addResult = await runCommand(
    "git",
    ["worktree", "add", "-b", branch, worktreePath, startPoint],
    { cwd: targetRepo }
  );

  if (addResult.exitCode !== 0) {
    throw new Error(`Failed to create worktree: ${addResult.stderr}`);
  }

  // If sparse checkout paths requested, configure sparse-checkout cone mode
  if (options.sparsePaths && options.sparsePaths.length > 0) {
    const initResult = await runCommand("git", ["sparse-checkout", "init", "--cone"], { cwd: worktreePath });
    if (initResult.exitCode !== 0) {
      throw new Error(`Failed to initialize sparse checkout: ${initResult.stderr}`);
    }
    const setResult = await runCommand("git", ["sparse-checkout", "set", ...options.sparsePaths], { cwd: worktreePath });
    if (setResult.exitCode !== 0) {
      throw new Error(`Failed to set sparse checkout paths: ${setResult.stderr}`);
    }
  }

  return {
    worktreeId,
    path: worktreePath,
    branch,
    baseBranch,
    createdAt: now,
  };
}

export interface WorktreeInfo {
  worktreeId: string;
  path: string;
  branch: string;
  ageSeconds: number;
  changedFilesCount: number;
  diskUsageBytes: number;
}

export async function listWorktrees(repoPath: string): Promise<WorktreeInfo[]> {
  const listResult = await runCommand("git", ["worktree", "list", "--porcelain"], { cwd: repoPath });
  if (listResult.exitCode !== 0) {
    throw new Error(`Failed to list worktrees: ${listResult.stderr}`);
  }

  const blocks = listResult.stdout.split("\n\n").map((b) => b.trim()).filter((b) => b.length > 0);
  const now = Date.now();
  const worktrees: WorktreeInfo[] = [];

  for (const block of blocks) {
    const lines = block.split("\n");
    let wtPath = "";
    let branch = "";

    for (const line of lines) {
      if (line.startsWith("worktree ")) {
        wtPath = line.substring(9).trim();
      } else if (line.startsWith("branch ")) {
        branch = line.substring(7).trim().replace(/^refs\/heads\//, "");
      } else if (line.startsWith("detached")) {
        branch = "detached";
      }
    }

    if (!wtPath) continue;

    // Filter for managed worktrees: contains .worktrees or boomtick-worktrees or branch starts with agent/ or folder wt-
    const folderName = path.basename(wtPath);
    const isManaged =
      wtPath.includes(".worktrees") ||
      wtPath.includes("boomtick-worktrees") ||
      folderName.startsWith("wt-") ||
      branch.startsWith("agent/");

    if (!isManaged) continue;

    // Extract worktreeId
    let worktreeId = folderName;
    if (!worktreeId.startsWith("wt-")) {
      worktreeId = `wt-${folderName}`;
    }

    // Check directory age
    let ageSeconds = 0;
    try {
      const stat = await fs.stat(wtPath);
      ageSeconds = Math.max(0, Math.floor((now - stat.birthtimeMs) / 1000));
      if (Number.isNaN(ageSeconds) || ageSeconds === 0) {
        ageSeconds = Math.max(0, Math.floor((now - stat.mtimeMs) / 1000));
      }
    } catch {
      // If stat fails, try to extract timestamp from wt-<name>-<timestamp>
      const match = worktreeId.match(/-(\d{10,13})$/);
      if (match) {
        const ts = parseInt(match[1], 10);
        const epochMs = ts > 1e12 ? ts : ts * 1000;
        ageSeconds = Math.max(0, Math.floor((now - epochMs) / 1000));
      }
    }

    // Measure disk usage
    const diskUsageBytes = await getDirectorySize(wtPath);

    // Count uncommitted changed files
    let changedFilesCount = 0;
    const statusRes = await runCommand("git", ["status", "--porcelain"], { cwd: wtPath });
    if (statusRes.exitCode === 0) {
      const changed = statusRes.stdout.split("\n").filter((l) => l.trim().length > 0);
      changedFilesCount = changed.length;
    }

    worktrees.push({
      worktreeId,
      path: wtPath,
      branch,
      ageSeconds,
      changedFilesCount,
      diskUsageBytes,
    });
  }

  return worktrees;
}

export async function removeWorktreeById(
  worktreeId: string,
  repoPath: string,
  force: boolean = false
): Promise<{ freedBytes: number; worktreeId: string }> {
  const worktrees = await listWorktrees(repoPath);
  const target = worktrees.find(
    (w) => w.worktreeId === worktreeId || path.basename(w.path) === worktreeId
  );

  if (!target) {
    throw new Error(`Worktree '${worktreeId}' not found.`);
  }

  // Refuse removal if uncommitted modifications exist and force is false
  if (!force && target.changedFilesCount > 0) {
    throw new Error(
      `Cannot remove worktree '${worktreeId}': has ${target.changedFilesCount} uncommitted modified files. Use force: true to remove.`
    );
  }

  const freedBytes = target.diskUsageBytes;

  const removeArgs = ["worktree", "remove"];
  if (force) {
    removeArgs.push("--force");
  }
  removeArgs.push(target.path);

  const removeResult = await runCommand("git", removeArgs, { cwd: repoPath });
  if (removeResult.exitCode !== 0) {
    // If git worktree remove fails, check if manual directory deletion is necessary
    if (force) {
      await fs.rm(target.path, { recursive: true, force: true });
    } else {
      throw new Error(`Failed to remove worktree: ${removeResult.stderr}`);
    }
  }

  await runCommand("git", ["worktree", "prune"], { cwd: repoPath });

  return {
    freedBytes,
    worktreeId,
  };
}

export async function getContractWorktreeTtl(repoPath: string): Promise<number> {
  const defaultTtl = 7 * 24 * 60 * 60; // 7 days in seconds
  try {
    const contractPath = path.join(repoPath, ".agents", "AGENT_CONTRACT.md");
    if (syncFs.existsSync(contractPath)) {
      const content = await fs.readFile(contractPath, "utf-8");
      const match = content.match(/worktree[_-]ttl[_-]seconds\s*[:=]\s*(\d+)/i) ||
                    content.match(/worktree[_-]ttl[_-]days\s*[:=]\s*(\d+)/i);
      if (match) {
        const val = parseInt(match[1], 10);
        if (content.toLowerCase().includes("ttl-days") || content.toLowerCase().includes("ttl_days")) {
          return val * 24 * 60 * 60;
        }
        return val;
      }
    }
  } catch {
    // Ignore and fallback
  }
  return defaultTtl;
}

export async function sweepStaleWorktrees(
  repoPath: string,
  ttlSeconds?: number
): Promise<{ sweptWorktreeIds: string[]; totalFreedBytes: number }> {
  const effectiveTtl = ttlSeconds !== undefined ? ttlSeconds : await getContractWorktreeTtl(repoPath);
  const worktrees = await listWorktrees(repoPath);
  const sweptWorktreeIds: string[] = [];
  let totalFreedBytes = 0;

  for (const wt of worktrees) {
    if (wt.ageSeconds >= effectiveTtl) {
      try {
        const result = await removeWorktreeById(wt.worktreeId, repoPath, true);
        sweptWorktreeIds.push(wt.worktreeId);
        totalFreedBytes += result.freedBytes;
      } catch {
        // Continue sweeping others if one fails
      }
    }
  }

  return {
    sweptWorktreeIds,
    totalFreedBytes,
  };
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
