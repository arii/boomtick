import { runCommand } from "../lib/shell.js";
import { z } from "zod";
import { getMergeConflictFiles, resolveRepoPath } from "../lib/git.js";

export const GetMergeConflictFilesInputSchema = z.object({
  prNumber: z.number().optional(),
  baseBranch: z.string().optional(),
  headRef: z.string().optional(),
  repo: z.string().optional().describe("Target GitHub repository override."),
  path: z.string().optional().describe("Local filesystem path to target repository root."),
  repoPath: z.string().optional().describe("Alias for path to target repository root."),
});

export async function getMergeConflictFilesHandler(args: z.infer<typeof GetMergeConflictFilesInputSchema>) {
  const targetCwd = resolveRepoPath({
    path: args.path,
    repoPath: args.repoPath,
    repo: args.repo,
  });

  let baseBranch = args.baseBranch;
  let headRef = args.headRef;

  // If prNumber is provided, inspect the PR metadata to determine the real head ref and base branch
  if (args.prNumber) {
    const ghArgs = [
      "pr",
      "view",
      args.prNumber.toString(),
      "--json", "headRefName,baseRefName"
    ];
    if (args.repo) {
      ghArgs.push("--repo", args.repo);
    }

    try {
      const prResult = await runCommand("gh", ghArgs, { cwd: targetCwd });
      if (prResult.exitCode === 0 && prResult.stdout.trim()) {
        const prInfo = JSON.parse(prResult.stdout);
        const resolvedHead = prInfo.headRefName;
        const resolvedBase = prInfo.baseRefName;

        if (!baseBranch && resolvedBase) {
          baseBranch = resolvedBase;
        }

        // If headRef is not explicitly set, default to PR's headRefName
        if (!headRef && resolvedHead) {
          headRef = resolvedHead;
        }

        // Fetch the remote branches so git merge-tree operates on up-to-date refs
        const fetchBase = baseBranch || resolvedBase;
        const fetchHead = headRef || resolvedHead;
        if (fetchBase) {
          await runCommand("git", ["fetch", "origin", fetchBase], { cwd: targetCwd });
        }
        if (fetchHead) {
          await runCommand("git", ["fetch", "origin", fetchHead], { cwd: targetCwd });
        }

        // Prefer comparing origin/<base> with origin/<head> if they were remote tracking branches
        if (fetchBase) {
          const checkBase = await runCommand("git", ["rev-parse", "--verify", `origin/${fetchBase}`], { cwd: targetCwd });
          if (checkBase.exitCode === 0) {
            baseBranch = `origin/${fetchBase}`;
          }
        }
        if (fetchHead) {
          const checkHead = await runCommand("git", ["rev-parse", "--verify", `origin/${fetchHead}`], { cwd: targetCwd });
          if (checkHead.exitCode === 0) {
            headRef = `origin/${fetchHead}`;
          }
        }
      }
    } catch {
      // Fallback if gh pr view fails
    }
  }

  // Fallbacks if not resolved
  const effectiveBaseBranch = baseBranch || "main";
  const effectiveHeadRef = headRef || "HEAD";

  const conflictFiles = await getMergeConflictFiles(effectiveBaseBranch, effectiveHeadRef, targetCwd);
  const hasConflicts = conflictFiles.length > 0;

  return {
    hasConflicts,
    conflictedFiles: conflictFiles,
    prNumber: args.prNumber ?? null,
    baseBranch: effectiveBaseBranch,
    headRef: effectiveHeadRef,
  };
}
