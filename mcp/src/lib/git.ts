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

export interface SessionWorktree {
  worktreeId: string;
  path: string;
  branch: string;
}

export async function createSessionWorktree(
  baseRepoPath: string,
  worktreeId: string,
  branch: string,
  baseBranch: string
): Promise<string> {
  if (!/^[A-Za-z0-9_.-]+$/.test(worktreeId)) {
    throw new Error(`Invalid worktree id: ${worktreeId}`);
  }
  const worktreePath = path.join(baseRepoPath, ".worktrees", worktreeId);
  if (syncFs.existsSync(worktreePath)) {
    throw new Error(`Worktree already exists: ${worktreePath}`);
  }
  await fs.mkdir(path.join(baseRepoPath, ".worktrees"), { recursive: true });
  const res = await runCommand(
    "git",
    ["worktree", "add", worktreePath, "-b", branch, baseBranch],
    { cwd: baseRepoPath }
  );
  if (res.exitCode !== 0) {
    throw new Error(`git worktree add failed: ${res.stderr}`);
  }
  return worktreePath;
}

export async function listSessionWorktrees(baseRepoPath: string): Promise<SessionWorktree[]> {
  const res = await runCommand("git", ["worktree", "list", "--porcelain"], { cwd: baseRepoPath });
  if (res.exitCode !== 0) {
    throw new Error(`git worktree list failed: ${res.stderr}`);
  }
  const managedRoot = path.join(baseRepoPath, ".worktrees") + path.sep;
  const out: SessionWorktree[] = [];
  let current: { path?: string; branch?: string } = {};
  const flush = () => {
    if (current.path && current.path.startsWith(managedRoot)) {
      out.push({
        worktreeId: path.basename(current.path),
        path: current.path,
        branch: (current.branch || "").replace(/^refs\/heads\//, ""),
      });
    }
    current = {};
  };
  for (const raw of res.stdout.split("\n")) {
    const line = raw.endsWith("\r") ? raw.slice(0, -1) : raw;
    if (line.startsWith("worktree ")) {
      if (current.path) flush();
      current = { path: line.slice("worktree ".length) };
    } else if (line.startsWith("branch ")) {
      current.branch = line.slice("branch ".length);
    } else if (line.trim() === "" && current.path) {
      flush();
    }
  }
  if (current.path) flush();
  return out;
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

  // First line is tree hash if successful or conflict output.
  // Filter out tree hash (40 or 64 hex characters).
  // Filter out git merge progress/informational messages:
  // "Auto-merging ...", "CONFLICT (...)", "Merge made by ...", etc.
  const files = lines.filter((line) => {
    if (/^[0-9a-f]{40,64}$/i.test(line)) return false;
    if (/^auto-merging\s+/i.test(line)) return false;
    if (/^conflict\s*\([^)]*\):/i.test(line)) return false;
    if (/^warning:/i.test(line)) return false;
    if (/^error:/i.test(line)) return false;
    if (/^hint:/i.test(line)) return false;
    return true;
  });

  return Array.from(new Set(files));
}
