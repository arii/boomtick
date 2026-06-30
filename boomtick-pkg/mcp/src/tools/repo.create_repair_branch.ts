import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { createWorktree } from "../lib/git.js";

export const CreateRepairBranchInputSchema = z.object({
  prNumber: z.number(),
  repairBranchName: z.string().optional(),
  writeMode: z.boolean().optional().default(false),
});

export async function createRepairBranchHandler(args: z.infer<typeof CreateRepairBranchInputSchema>) {
  if (!args.writeMode) {
    throw new Error("writeMode must be true to create a repair branch.");
  }
  const prResult = await runCommand("gh", [
    "pr",
    "view",
    args.prNumber.toString(),
    "--json", "headRefName,baseRefName,title"
  ]);

  if (prResult.exitCode !== 0) {
    throw new Error(`Failed to get PR info: ${prResult.stderr}`);
  }

  const { headRefName, baseRefName, title } = JSON.parse(prResult.stdout);

  const sanitizedTitle = title.toLowerCase().replace(/[^a-z0-9]/g, "-").substring(0, 30);
  const repairBranch = args.repairBranchName || `agent/repair-pr-${args.prNumber}-${sanitizedTitle}`;

  // Ensure latest
  await runCommand("git", ["fetch", "origin", headRefName]);
  await runCommand("git", ["fetch", "origin", baseRefName]);

  const worktreePath = await createWorktree(`origin/${headRefName}`, args.prNumber);

  // Create the actual repair branch in the worktree
  await runCommand("git", ["checkout", "-b", repairBranch], { cwd: worktreePath });

  return {
    prNumber: args.prNumber,
    originalBranch: headRefName,
    repairBranch,
    baseBranch: baseRefName,
    worktreePath
  };
}
