import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { resolveRepo } from "../lib/git.js";
import { sanitizeError } from "../lib/error_utils.js";

export const GetPrInputSchema = z.object({
  prNumber: z.number().describe("The number of the PR to view."),
  repo: z.string().optional().describe("The target repository override (e.g. org/repo)."),
});

export async function getPrHandler(args: z.infer<typeof GetPrInputSchema>) {
  const params = GetPrInputSchema.parse(args);
  const targetRepo = resolveRepo(params.repo);

  const result = await runCommand("td-cli", ["gh", "view", params.prNumber.toString(), "--repo", targetRepo]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to get PR details: ${sanitizeError(result.stderr)}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to get PR details: ${output.message}`);
  }

  return { pr: output.pr };
}
