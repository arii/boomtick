import { z } from "zod";
import { runTDCli } from "../lib/tdCli.js";

export const ReadCiLogsInputSchema = z.object({
  prNumber: z.number().optional().describe("PR number for CI logs. Omit with includeRuns to list workflow runs instead."),
  all: z.boolean().optional(),
  repo: z.string().optional(),
  includeRuns: z.boolean().optional().describe("Include recent workflow runs (absorbs repo_get_workflow_runs)."),
  branch: z.string().optional().describe("Filter workflow runs by branch name."),
  event: z.string().optional().describe("Filter workflow runs by event (e.g. push, pull_request)."),
});

export async function readCiLogsHandler(args: z.infer<typeof ReadCiLogsInputSchema>) {
  const parsed = ReadCiLogsInputSchema.parse(args);
  if (parsed.prNumber === undefined) {
    const cliArgs = ["repo", "workflow-runs"];
    if (parsed.repo) {
      cliArgs.push("--repo", parsed.repo);
    }
    if (parsed.branch) {
      cliArgs.push("--branch", parsed.branch);
    }
    if (parsed.event) {
      cliArgs.push("--event", parsed.event);
    }
    const runs = await runTDCli(cliArgs, "fetch workflow runs");
    return { workflowRuns: runs.workflow_runs };
  }
  const params = ["repo", "ci-logs", parsed.prNumber.toString()];
  if (parsed.all) {
    params.push("--all");
  }
  if (parsed.repo) {
    params.push("--repo", parsed.repo);
  }
  const output = await runTDCli(params);

  const response: Record<string, unknown> = {
    checks: output.checks,
    failedChecks: output.failedChecks,
    logs: output.logs
  };
  if (parsed.includeRuns) {
    const cliArgs = ["repo", "workflow-runs"];
    if (parsed.repo) {
      cliArgs.push("--repo", parsed.repo);
    }
    if (parsed.branch) {
      cliArgs.push("--branch", parsed.branch);
    }
    if (parsed.event) {
      cliArgs.push("--event", parsed.event);
    }
    const runs = await runTDCli(cliArgs, "fetch workflow runs");
    response.workflowRuns = runs.workflow_runs;
  }
  return response;
}
