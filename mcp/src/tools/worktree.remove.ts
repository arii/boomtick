import { WorktreeRemoveInput, WorktreeRemoveInputSchema } from "./contract.js";
import { resolveRepoPath, removeWorktree, dirSizeBytes } from "../lib/git.js";
import { SessionManager } from "../lib/session_manager.js";
import { runCommand } from "../lib/shell.js";
import path from "path";
import * as syncFs from "fs";

export { WorktreeRemoveInputSchema };

export async function worktreeRemoveHandler(args: WorktreeRemoveInput) {
  const parsed = WorktreeRemoveInputSchema.parse(args);
  if (parsed.writeMode !== true) {
    throw new Error("writeMode must be true to remove a worktree");
  }
  if (!/^[A-Za-z0-9_.-]+$/.test(parsed.worktreeId)) {
    throw new Error(`Invalid worktree id: ${parsed.worktreeId}`);
  }
  const baseRepoPath = resolveRepoPath({ repo: parsed.repo ?? null, path: parsed.path ?? null });
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
  let freedBytes: number | null = null;
  try {
    freedBytes = dirSizeBytes(worktreePath);
  } catch {
    // Best effort; removal proceeds.
  }
  // Sessions bound to this worktree end first: no live executor may
  // outlive its root (#1099).
  const abandoned = await SessionManager.getInstance()
    .abandonSessionsInWorktree(worktreePath);
  await removeWorktree(worktreePath, baseRepoPath);

  return {
    status: "removed",
    worktreeId: parsed.worktreeId,
    freedBytes,
    abandonedSessions: abandoned,
  };
}
