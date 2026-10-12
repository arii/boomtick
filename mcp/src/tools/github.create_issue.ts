import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { resolveRepo } from "../lib/git.js";
import { sanitizeError } from "../lib/error_utils.js";
import { CreateIssueInputSchema, CreateIssueResponseSchema } from "./contract.js";

export { CreateIssueInputSchema };

export async function createIssueHandler(args: z.input<typeof CreateIssueInputSchema>) {
  const params = CreateIssueInputSchema.parse(args);
  const targetRepo = resolveRepo(params.repo);

  const cmdArgs = ["gh", "create-issue", "--title", params.title];
  if (params.body) cmdArgs.push("--body", params.body);
  if (params.file) cmdArgs.push("--file", params.file);
  cmdArgs.push("--repo", targetRepo);

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
