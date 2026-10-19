import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { resolveRepo } from "../lib/git.js";
import { sanitizeError } from "../lib/error_utils.js";

const GetPrReviewsInputSchema = z.object({
  prNumber: z.number().describe("The number of the PR to view reviews for."),
  repo: z.string().optional().describe("The target repository override (e.g. org/repo)."),
});

export async function getPrReviewsHandler(args: z.infer<typeof GetPrReviewsInputSchema>) {
  const params = GetPrReviewsInputSchema.parse(args);
  const targetRepo = resolveRepo(params.repo);

  const result = await runCommand("td-cli", ["gh", "read-pr-reviews", "--pr-number", params.prNumber.toString(), "--repo", targetRepo]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to read PR reviews: ${sanitizeError(result.stderr)}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to read PR reviews: ${output.message}`);
  }

  return { reviews: output.reviews, reviewCount: output.review_count };
}
