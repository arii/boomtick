import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { sanitizeError } from "../lib/error_utils.js";
import { IssueUpdateInputSchema, IssueUpdateResponseSchema } from "./contract.js";

export { IssueUpdateInputSchema };

export async function issueUpdateHandler(args: any) {
  const params = IssueUpdateInputSchema.parse(args);

  const cmdArgs = ["gh", "issue-update", params.issueNumber.toString()];
  if (params.body) cmdArgs.push("--body", params.body);
  if (params.file) cmdArgs.push("--file", params.file);
  if (params.labels && params.labels.length > 0) cmdArgs.push("--labels", params.labels.join(","));
  if (params.addLabels && params.addLabels.length > 0) cmdArgs.push("--add-labels", params.addLabels.join(","));
  if (params.removeLabels && params.removeLabels.length > 0) cmdArgs.push("--remove-labels", params.removeLabels.join(","));
  if (params.state) cmdArgs.push("--state", params.state);

  const result = await runCommand("td-cli", cmdArgs);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to update issue: ${sanitizeError(result.stderr)}`);
  }

  const output = IssueUpdateResponseSchema.parse(JSON.parse(result.stdout));
  if (output.status === "error") {
    throw new Error(`Failed to update issue: ${output.message}`);
  }

  return { status: "success", issue: output.issue };
}
