import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { sanitizeError } from "../lib/error_utils.js";

export const IssueUpdateInputSchema = z.object({
  issueNumber: z.number().describe("The number of the issue to update."),
  body: z.string().min(1, "Issue body cannot be empty").describe("The new body content for the issue."),
});

const IssueUpdateOutputSchema = z.object({
  status: z.string(),
  issue: z.any().optional(),
  message: z.string().optional(),
});

export async function issueUpdateHandler(args: z.infer<typeof IssueUpdateInputSchema>) {
  const params = IssueUpdateInputSchema.parse(args);

  const result = await runCommand("td-cli", ["gh", "issue-update", params.issueNumber.toString(), "--body", params.body]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to update issue: ${sanitizeError(result.stderr)}`);
  }

  const output = IssueUpdateOutputSchema.parse(JSON.parse(result.stdout));
  if (output.status === "error") {
    throw new Error(`Failed to update issue: ${output.message}`);
  }

  return { status: "success", issue: output.issue };
}
