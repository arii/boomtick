import { z } from "zod";
import { resolveRepo } from "../lib/git.js";
import { runTDCli } from "./jules/cli.js";

export const GetPrDiffInputSchema = z.object({
  prNumber: z.number().describe("The number of the pull request to get the diff for."),
  repo: z.string().optional().describe("The target repository override (e.g. org/repo)."),
});

export async function getPrDiffHandler(args: z.infer<typeof GetPrDiffInputSchema>) {
  const params = GetPrDiffInputSchema.parse(args);
  const targetRepo = resolveRepo(params.repo);

  const output = await runTDCli([
    "gh", "pr-diff", params.prNumber.toString(), "--repo", targetRepo
  ], "get PR diff");

  return {
    prNumber: output.prNumber,
    files: output.files,
    diffText: output.diffText,
    isTruncated: output.isTruncated
  };
}
