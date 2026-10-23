import { z } from "zod";
import { runTDCli } from "./jules/cli.js";

export const CommentTriageSummaryInputSchema = z.object({
  prNumber: z.number(),
  body: z.string(),
});

export async function commentTriageSummaryHandler(args: z.infer<typeof CommentTriageSummaryInputSchema>) {
  const output = await runTDCli([
    "gh",
    "post-comment",
    "--pr", args.prNumber.toString(),
    "--body", args.body
  ], "comment on PR");

  return {
    success: true,
    commentUrl: output.html_url || output.url
  };
}
