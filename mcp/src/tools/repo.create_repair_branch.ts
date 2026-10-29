import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { createWorktree, resolveRepoPath } from "../lib/git.js";

export const CreateRepairBranchInputSchema = z.object({
  prNumber: z.number(),
  repairBranchName: z.string().optional(),
  writeMode: z.boolean().optional().default(false),
  repo: z.string().optional().describe("Target repository override (e.g. org/repo or repo)."),
  path: z.string().optional().describe("Local filesystem path to target repository root."),
  repoPath: z.string().optional().describe("Alias for path to target repository root."),
});

export async function createRepairBranchHandler(args: z.infer<typeof CreateRepairBranchInputSchema>) {
  if (!args.writeMode) {
    throw new Error("writeMode must be true to create a repair branch.");
  }

  const targetCwd = resolveRepoPath({
    path: args.path,
    repoPath: args.repoPath,
    repo: args.repo,
  });

  const ghArgs = [
    "pr",
    "view",
    args.prNumber.toString(),
    "--json", "headRefName,baseRefName,title"
  ];
  if (args.repo) {
    ghArgs.push("--repo", args.repo);
  }

  const prResult = await runCommand("gh", ghArgs, { cwd: targetCwd });

  if (prResult.exitCode !== 0) {
    throw new Error(`Failed to get PR info: ${prResult.stderr}`);
  }

  const { headRefName, baseRefName, title } = JSON.parse(prResult.stdout);

  const sanitizedTitle = title.toLowerCase().replace(/[^a-z0-9]/g, "-").substring(0, 30);
  const repairBranch = args.repairBranchName || `agent/repair-pr-${args.prNumber}-${sanitizedTitle}`;

  // Ensure latest in target repo
  await runCommand("git", ["fetch", "origin", headRefName], { cwd: targetCwd });
  await runCommand("git", ["fetch", "origin", baseRefName], { cwd: targetCwd });

  const worktreePath = await createWorktree(`origin/${headRefName}`, args.prNumber, targetCwd);

  // Create the actual repair branch in the worktree
  await runCommand("git", ["checkout", "-b", repairBranch], { cwd: worktreePath });

  const response: Record<string, unknown> = {
    prNumber: args.prNumber,
    originalBranch: headRefName,
    repairBranch,
    baseBranch: baseRefName,
    worktreePath,
    path: targetCwd,
  };

  if (args.repo) {
    response.repo = args.repo;
  }

  return response;
}
