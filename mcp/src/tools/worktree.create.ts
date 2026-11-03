import { WorktreeCreateInput, WorktreeCreateInputSchema } from "./contract.js";
import { resolveRepoPath, createSessionWorktree } from "../lib/git.js";
import crypto from "crypto";

export { WorktreeCreateInputSchema };

export async function worktreeCreateHandler(args: WorktreeCreateInput) {
  const parsed = WorktreeCreateInputSchema.parse(args);
  const baseRepoPath = resolveRepoPath({ repo: parsed.repo ?? null });
  const worktreeId = `wt-${crypto.randomBytes(4).toString("hex")}`;
  const worktreePath = await createSessionWorktree(
    baseRepoPath,
    worktreeId,
    parsed.branch,
    parsed.baseBranch ?? "main"
  );

  return {
    worktreeId,
    path: worktreePath,
    branch: parsed.branch,
  };
}
