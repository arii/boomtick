import { z } from "zod";
import { resolveRepoPath, removeWorktreeById } from "../lib/git.js";
import { WorktreeRemoveInputSchema } from "./contract.js";

export { WorktreeRemoveInputSchema };

export async function worktreeRemoveHandler(args: z.infer<typeof WorktreeRemoveInputSchema>) {
  if (!args.writeMode) {
    throw new Error("writeMode must be true to remove a worktree.");
  }

  const targetRepo = resolveRepoPath({
    path: args.path,
    repo: args.repo,
  });

  const result = await removeWorktreeById(args.worktreeId, targetRepo, args.force);

  return {
    status: "removed",
    worktreeId: result.worktreeId,
    freedBytes: result.freedBytes,
  };
}
