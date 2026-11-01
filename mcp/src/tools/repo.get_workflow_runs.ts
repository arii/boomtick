import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { resolveRepo } from "../lib/git.js";
import { sanitizeError } from "../lib/error_utils.js";

export const GetWorkflowRunsInputSchema = z.object({
  branch: z.string().optional().describe("Filter workflow runs by branch name."),
  event: z.string().optional().describe("Filter workflow runs by event (e.g. push, pull_request)."),
  repo: z
    .string()
    .regex(/^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/)
    .optional()
    .describe(
      "The target GitHub repository in owner/repo format (e.g. 'arii/remote-server'). Omit or pass null to use the current repository context."
    ),
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

  let output: any = null;
  if (result.stdout && result.stdout.trim().startsWith("{")) {
    try {
      output = JSON.parse(result.stdout);
    } catch {
      // ignore JSON parse error
    }
  }

  if (output && output.status === "error") {
    const msg = output.message || "Unknown error";
    if (msg.includes("Not Found") || output.code === 404) {
      throw new Error(`Repository '${targetRepo}' not found (404)`);
    }
    throw new Error(`Failed to fetch workflow runs: ${msg}`);
  }

  if (result.exitCode !== 0) {
    const errText = sanitizeError(result.stderr) || sanitizeError(result.stdout) || "Unknown error";
    if (errText.includes("Not Found") || errText.includes("404")) {
      throw new Error(`Repository '${targetRepo}' not found (404)`);
    }
    throw new Error(`Failed to fetch workflow runs: ${errText}`);
  }

  if (!output || !output.workflow_runs) {
    throw new Error("Failed to fetch workflow runs: Invalid output format");
  }

  return { workflowRuns: output.workflow_runs };
}
