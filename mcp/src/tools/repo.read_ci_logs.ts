import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const ReadCiLogsInputSchema = z.object({
  prNumber: z.number(),
  all: z.boolean().optional(),
});

export async function readCiLogsHandler(args: z.infer<typeof ReadCiLogsInputSchema>) {
  ReadCiLogsInputSchema.parse(args);
  const params = ["repo", "ci-logs", args.prNumber.toString()];
  if (args.all) {
    params.push("--all");
  }
  const result = await runCommand("td-cli", params);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to get CI logs: ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to get CI logs: ${output.message}`);
  }

  return {
    checks: output.checks,
    failedChecks: output.failedChecks,
    logs: output.logs
  };
}
