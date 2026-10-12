import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { resolveRepo } from "../lib/git.js";

export const GetPrDiffInputSchema = z.object({
  prNumber: z.number().describe("The number of the pull request to get the diff for."),
  repo: z.string().optional().describe("The target repository override (e.g. org/repo)."),
});

export async function getPrDiffHandler(args: z.infer<typeof GetPrDiffInputSchema>) {
  const params = GetPrDiffInputSchema.parse(args);
  const targetRepo = resolveRepo(params.repo);

  const result = await runCommand("td-cli", [
    "gh", "pr-diff", params.prNumber.toString(), "--repo", targetRepo
  ]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to get PR diff: ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to get PR diff: ${output.message}`);
  }

  // Every TypeScript tool file must be a pure routing shim
  return {
    prNumber: output.prNumber,
    files: output.files,
    diffText: output.diffText,
    isTruncated: output.isTruncated
  };
}
