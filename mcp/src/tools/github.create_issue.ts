import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { sanitizeError } from "../lib/error_utils.js";
import { CreateIssueInputSchema, CreateIssueResponseSchema } from "./contract.js";

export { CreateIssueInputSchema };

export async function createIssueHandler(args: z.infer<typeof CreateIssueInputSchema>) {
  const params = CreateIssueInputSchema.parse(args);

  const cmdArgs = ["gh", "create-issue", "--title", params.title];
  if (params.body) cmdArgs.push("--body", params.body);
  if (params.file) cmdArgs.push("--file", params.file);

  const result = await runCommand("td-cli", cmdArgs);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to create issue: ${sanitizeError(result.stderr)}`);
  }

  let output;
  try {
    output = JSON.parse(result.stdout);
  } catch (e) {
    throw new Error(`Failed to parse CLI output: ${result.stdout}`);
  }

  const parsedOutput = CreateIssueResponseSchema.parse(output);
  if (parsedOutput.status === "error") {
    throw new Error(`Failed to create issue: ${parsedOutput.message}`);
  }

  return { status: "success", issue: parsedOutput.issue };
}
