import { WorktreeListInput, WorktreeListInputSchema } from "./contract.js";
import { resolveRepoPath, listSessionWorktrees } from "../lib/git.js";

export { WorktreeListInputSchema };

export async function worktreeListHandler(args: WorktreeListInput) {
  const parsed = WorktreeListInputSchema.parse(args);
  const baseRepoPath = resolveRepoPath({ repo: parsed.repo ?? null });
  const worktrees = await listSessionWorktrees(baseRepoPath);

  return { worktrees };
}
