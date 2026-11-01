import { z } from "zod";
import { resolveRepoPath, listWorktrees, sweepStaleWorktrees } from "../lib/git.js";
import { WorktreeListInputSchema } from "./contract.js";

export { WorktreeListInputSchema };

export async function worktreeListHandler(args: Partial<z.infer<typeof WorktreeListInputSchema>> = {}) {
  const targetRepo = resolveRepoPath({
    path: args.path,
    repo: args.repo,
  });

  // Run automated TTL sweep before listing
  try {
    await sweepStaleWorktrees(targetRepo);
  } catch {
    // Gracefully proceed if sweep fails
  }

  const worktrees = await listWorktrees(targetRepo);
  return {
    worktrees,
  };
}
