import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const CheckoutBranchInputSchema = z.object({
  branch: z.string(),
  worktreePath: z.string().optional(),
});

export async function checkoutBranchHandler(args: z.infer<typeof CheckoutBranchInputSchema>) {
  const result = await runCommand("git", ["checkout", args.branch], { cwd: args.worktreePath });

  if (result.exitCode !== 0) {
    throw new Error(`Failed to checkout branch ${args.branch}: ${result.stderr}`);
  }

  return {
    success: true,
    branch: args.branch
  };
}
