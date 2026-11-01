import { z } from "zod";
import { resolveRepoPath, createManagedWorktree } from "../lib/git.js";
import { WorktreeCreateInputSchema } from "./contract.js";

export { WorktreeCreateInputSchema };

export async function worktreeCreateHandler(args: z.infer<typeof WorktreeCreateInputSchema>) {
  if (!args.writeMode) {
    throw new Error("writeMode must be true to create a worktree.");
  }

  const targetRepo = resolveRepoPath({
    path: args.path,
    repo: args.repo,
  });

  const result = await createManagedWorktree({
    targetRepoPath: targetRepo,
    name: args.name,
    baseBranch: args.baseBranch,
    sparsePaths: args.sparsePaths,
  });

  return {
    worktreeId: result.worktreeId,
    path: result.path,
    branch: result.branch,
    baseBranch: result.baseBranch,
    createdAt: result.createdAt,
  };
}
