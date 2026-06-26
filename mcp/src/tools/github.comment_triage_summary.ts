import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const CommentTriageSummaryInputSchema = z.object({
  prNumber: z.number(),
  body: z.string(),
});

export async function commentTriageSummaryHandler(args: z.infer<typeof CommentTriageSummaryInputSchema>) {
  const result = await runCommand("gh", [
    "pr",
    "comment",
    args.prNumber.toString(),
    "--body", args.body
  ]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to comment on PR: ${result.stderr}`);
  }

  return {
    success: true,
    commentUrl: result.stdout.trim()
  };
}
