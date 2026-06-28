import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const CreateBranchInputSchema = z.object({
  branchName: z.string(),
  baseBranch: z.string().optional().default("main"),
});

export async function createBranchHandler(args: z.input<typeof CreateBranchInputSchema>) {
  const params = CreateBranchInputSchema.parse(args);

  // Ensure latest base branch
  await runCommand("git", ["fetch", "origin", params.baseBranch]);

  // Create branch from origin base branch
  const result = await runCommand("git", ["checkout", "-b", params.branchName, `origin/${params.baseBranch}`]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to create branch ${params.branchName}: ${result.stderr}`);
  }

  return {
    success: true,
    branchName: params.branchName,
    baseBranch: params.baseBranch
  };
}
