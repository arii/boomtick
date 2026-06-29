import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { sanitizeError } from "../lib/error_utils.js";

export const CreateIssueInputSchema = z.object({
  title: z.string().min(1, "Issue title cannot be empty").describe("The title of the issue."),
  body: z.string().min(1, "Issue body cannot be empty").describe("The body/description of the issue."),
});

const CreateIssueOutputSchema = z.object({
  status: z.string(),
  issue: z.object({
    number: z.number(),
    title: z.string(),
    html_url: z.string(),
    state: z.string(),
  }).optional(),
  message: z.string().optional(),
});

export async function createIssueHandler(args: z.infer<typeof CreateIssueInputSchema>) {
  const params = CreateIssueInputSchema.parse(args);

  const result = await runCommand("td-cli", ["gh", "create-issue", "--title", params.title, "--body", params.body]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to create issue: ${sanitizeError(result.stderr)}`);
  }

  let output;
  try {
    output = JSON.parse(result.stdout);
  } catch (e) {
    throw new Error(`Failed to parse CLI output: ${result.stdout}`);
  }

  const parsedOutput = CreateIssueOutputSchema.parse(output);
  if (parsedOutput.status === "error") {
    throw new Error(`Failed to create issue: ${parsedOutput.message}`);
  }

  return { status: "success", issue: parsedOutput.issue };
}
