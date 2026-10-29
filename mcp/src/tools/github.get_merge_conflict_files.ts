import { z } from "zod";
import { getMergeConflictFiles, resolveRepoPath } from "../lib/git.js";

export const GetMergeConflictFilesInputSchema = z.object({
  prNumber: z.number().optional(),
  baseBranch: z.string().optional().default("main"),
  headRef: z.string().optional().default("HEAD"),
  repo: z.string().optional().describe("Target GitHub repository override."),
  path: z.string().optional().describe("Local filesystem path to target repository root."),
  repoPath: z.string().optional().describe("Alias for path to target repository root."),
});

export async function getMergeConflictFilesHandler(args: z.infer<typeof GetMergeConflictFilesInputSchema>) {
  const baseBranch = args.baseBranch || "main";
  const headRef = args.headRef || "HEAD";
  const targetCwd = resolveRepoPath({
    path: args.path,
    repoPath: args.repoPath,
    repo: args.repo,
  });

  const conflictFiles = await getMergeConflictFiles(baseBranch, headRef, targetCwd);

  const hasConflicts = conflictFiles.length > 0;

  return {
    hasConflicts,
    conflictedFiles: conflictFiles,
    prNumber: args.prNumber ?? null,
    baseBranch,
    headRef,
  };
}
