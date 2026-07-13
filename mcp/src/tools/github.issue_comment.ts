import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { sanitizeError } from "../lib/error_utils.js";

export const IssueCommentInputSchema = z.object({
  issueNumber: z.number().describe("The number of the issue to comment on."),
  body: z.string().min(1, "Comment body cannot be empty").describe("The content of the comment."),
});

const IssueCommentOutputSchema = z.object({
  status: z.string(),
  comment: z.any().optional(),
  message: z.string().optional(),
});

export async function issueCommentHandler(args: z.infer<typeof IssueCommentInputSchema>) {
  const params = IssueCommentInputSchema.parse(args);

  const result = await runCommand("td-cli", ["gh", "issue-comment", params.issueNumber.toString(), "--body", params.body]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to post comment: ${sanitizeError(result.stderr)}`);
  }

  const output = IssueCommentOutputSchema.parse(JSON.parse(result.stdout));
  if (output.status === "error") {
    throw new Error(`Failed to post comment: ${output.message}`);
  }

  return { status: "success", comment: output.comment };
}
