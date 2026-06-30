import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const CommentTriageSummaryInputSchema = z.object({
  prNumber: z.number(),
  body: z.string(),
});

export async function commentTriageSummaryHandler(args: z.infer<typeof CommentTriageSummaryInputSchema>) {
  const result = await runCommand("td-cli", [
    "gh",
    "post-comment",
    "--pr", args.prNumber.toString(),
    "--body", args.body
  ]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to comment on PR: ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to comment on PR: ${output.message}`);
  }

  return {
    success: true,
    commentUrl: output.html_url || output.url
  };
}
