import { WorktreeListInput, WorktreeListInputSchema } from "./contract.js";
import { resolveRepoPath, listSessionWorktrees, dirSizeBytes } from "../lib/git.js";
import { runCommand } from "../lib/shell.js";
import * as syncFs from "fs";

export { WorktreeListInputSchema };

export async function worktreeListHandler(args: WorktreeListInput) {
  const parsed = WorktreeListInputSchema.parse(args);
  const baseRepoPath = resolveRepoPath({ repo: parsed.repo ?? null, path: parsed.path ?? null });
  const worktrees = await listSessionWorktrees(baseRepoPath);

  const items = [];
  for (const wt of worktrees) {
    const statusRes = await runCommand("git", ["status", "--porcelain"], { cwd: wt.path });
    const changedFilesCount =
      statusRes.exitCode === 0
        ? statusRes.stdout.split("\n").filter((l) => l.trim().length > 0).length
        : 0;
    let ageSeconds = 0;
    try {
      ageSeconds = Math.max(0, Math.floor((Date.now() - syncFs.statSync(wt.path).mtimeMs) / 1000));
    } catch {
      // Worktree vanished mid-list; report zeros.
    }
    let diskUsageBytes = 0;
    try {
      diskUsageBytes = dirSizeBytes(wt.path);
    } catch {
      // Same as above.
    }
    items.push({
      worktreeId: wt.worktreeId,
      path: wt.path,
      branch: wt.branch,
      ageSeconds,
      changedFilesCount,
      diskUsageBytes,
    });
  }

  return { worktrees: items };
}
