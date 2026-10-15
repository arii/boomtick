import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { resolveRepo } from "../lib/git.js";
import { sanitizeError } from "../lib/error_utils.js";

export const GetPrCommitsInputSchema = z.object({
  prNumber: z.number().describe("The number of the PR to list commits for."),
  repo: z.string().optional().describe("The target repository override (e.g. org/repo)."),
});

export async function getPrCommitsHandler(args: z.infer<typeof GetPrCommitsInputSchema>) {
  const params = GetPrCommitsInputSchema.parse(args);
  const targetRepo = resolveRepo(params.repo);

  const result = await runCommand("td", ["gh", "list-pr-commits", "--pr-number", params.prNumber.toString(), "--repo", targetRepo]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to list PR commits: ${sanitizeError(result.stderr)}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to list PR commits: ${output.message}`);
  }

  return { commits: output.commits };
}
