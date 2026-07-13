import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const CheckoutBranchInputSchema = z.object({
  branch: z.string(),
  worktreePath: z.string().optional(),
});

export async function checkoutBranchHandler(args: z.infer<typeof CheckoutBranchInputSchema>) {
  const result = await runCommand("td-cli", ["gh", "checkout", args.branch], { cwd: args.worktreePath });

  if (result.exitCode !== 0) {
    throw new Error(`Failed to checkout branch ${args.branch}: ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to checkout branch: ${output.message}`);
  }

  return {
    success: true,
    branch: args.branch
  };
}
