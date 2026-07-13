import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { sanitizeError } from "../lib/error_utils.js";

export const GetPrInputSchema = z.object({
  prNumber: z.number().describe("The number of the PR to view."),
});

export async function getPrHandler(args: z.infer<typeof GetPrInputSchema>) {
  const params = GetPrInputSchema.parse(args);

  const result = await runCommand("td-cli", ["gh", "view", params.prNumber.toString()]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to get PR details: ${sanitizeError(result.stderr)}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to get PR details: ${output.message}`);
  }

  return { pr: output.pr };
}
