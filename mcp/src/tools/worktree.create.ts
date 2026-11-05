import { WorktreeCreateInput, WorktreeCreateInputSchema } from "./contract.js";
import { resolveRepoPath, createSessionWorktree } from "../lib/git.js";
import { ensureSharedDependencies } from "../lib/dependency_cache.js";
import { runCommand } from "../lib/shell.js";
import crypto from "crypto";

export { WorktreeCreateInputSchema };

export function sanitizeBranchName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export async function worktreeCreateHandler(args: WorktreeCreateInput) {
  const parsed = WorktreeCreateInputSchema.parse(args);
  if (parsed.writeMode !== true) {
    throw new Error("writeMode must be true to create a worktree");
  }
  const baseRepoPath = resolveRepoPath({ repo: parsed.repo ?? null, path: parsed.path ?? null });
  const worktreeId = `wt-${crypto.randomBytes(4).toString("hex")}`;
  const slug = parsed.name ? sanitizeBranchName(parsed.name) : "";
  const branch = slug || `wt-${worktreeId.slice(3)}`;
  const baseBranch = parsed.baseBranch || "main";
  const worktreePath = await createSessionWorktree(baseRepoPath, worktreeId, branch, baseBranch);
  if (parsed.sparsePaths && parsed.sparsePaths.length > 0) {
    const res = await runCommand("git", ["sparse-checkout", "set", ...parsed.sparsePaths], {
      cwd: worktreePath,
    });
    if (res.exitCode !== 0) {
      throw new Error(`git sparse-checkout failed: ${res.stderr}`);
    }
  }

  let depsWarmed = false;
  let depsNote = "skipped";
  try {
    await ensureSharedDependencies({ repoPath: baseRepoPath, worktreePath, config: {} });
    depsWarmed = true;
    depsNote = "shared dependencies linked";
  } catch (e) {
    depsNote = `dependency warming failed: ${e instanceof Error ? e.message : String(e)}`;
  }

  return {
    worktreeId,
    path: worktreePath,
    branch,
    baseBranch,
    createdAt: Date.now(),
    depsWarmed,
    depsNote,
  };
}
