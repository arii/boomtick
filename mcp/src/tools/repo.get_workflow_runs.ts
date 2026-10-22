import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { resolveRepo } from "../lib/git.js";
import { sanitizeError } from "../lib/error_utils.js";

const GetWorkflowRunsInputSchema = z.object({
  branch: z.string().optional().describe("Filter workflow runs by branch name."),
  event: z.string().optional().describe("Filter workflow runs by event (e.g. push, pull_request)."),
  repo: z.string().optional().describe("The target repository override (e.g. org/repo)."),
});

export async function getWorkflowRunsHandler(args: z.infer<typeof GetWorkflowRunsInputSchema>) {
  const params = GetWorkflowRunsInputSchema.parse(args);
  const targetRepo = resolveRepo(params.repo);

  const cliArgs = ["repo", "workflow-runs", "--repo", targetRepo];
  if (params.branch) {
    cliArgs.push("--branch", params.branch);
  }
  if (params.event) {
    cliArgs.push("--event", params.event);
  }

  const result = await runCommand("td", cliArgs);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to fetch workflow runs: ${sanitizeError(result.stderr)}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to fetch workflow runs: ${output.message}`);
  }

  return { workflowRuns: output.workflow_runs };
}
