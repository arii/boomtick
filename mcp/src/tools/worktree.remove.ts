import { WorktreeRemoveInput, WorktreeRemoveInputSchema } from "./contract.js";
import { resolveRepoPath, removeWorktree } from "../lib/git.js";
import { runCommand } from "../lib/shell.js";
import path from "path";
import * as syncFs from "fs";

export { WorktreeRemoveInputSchema };

export async function worktreeRemoveHandler(args: WorktreeRemoveInput) {
  const parsed = WorktreeRemoveInputSchema.parse(args);
  if (!/^[A-Za-z0-9_.-]+$/.test(parsed.worktreeId)) {
    throw new Error(`Invalid worktree id: ${parsed.worktreeId}`);
  }
  const baseRepoPath = resolveRepoPath({ repo: parsed.repo ?? null });
  const worktreePath = path.join(baseRepoPath, ".worktrees", parsed.worktreeId);
  if (!syncFs.existsSync(worktreePath)) {
    throw new Error(`Worktree not found: ${parsed.worktreeId}`);
  }
  if (!parsed.force) {
    const statusRes = await runCommand("git", ["status", "--porcelain"], { cwd: worktreePath });
    if (statusRes.exitCode === 0 && statusRes.stdout.trim().length > 0) {
      throw new Error(`Worktree ${parsed.worktreeId} has uncommitted changes; pass force=true to remove anyway`);
    }
  }
  await removeWorktree(worktreePath, baseRepoPath);

  return {
    worktreeId: parsed.worktreeId,
    removed: true,
  };
}
