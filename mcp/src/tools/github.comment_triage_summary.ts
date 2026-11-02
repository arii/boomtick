import { z } from "zod";
import { runTDCli } from "./jules/cli.js";

export const CommentTriageSummaryInputSchema = z.object({
  prNumber: z.number(),
  body: z.string(),
  repo: z.string().optional().describe("The target repository override (e.g. org/repo)."),
});

export async function commentTriageSummaryHandler(args: z.infer<typeof CommentTriageSummaryInputSchema>) {
  const cliArgs = [
    "gh",
    "post-comment",
    "--pr", args.prNumber.toString(),
    "--body", args.body
  ];

  if (args.repo) {
    cliArgs.push("--repo", args.repo);
  }

  const output = await runTDCli(cliArgs, "comment on PR");

  return {
    success: true,
    commentUrl: output.html_url || output.url
  };
}
