import { z } from "zod";
import { runTDCli } from "../lib/td-cli.js";

export const ReadCiLogsInputSchema = z.object({
  prNumber: z.number(),
  all: z.boolean().optional(),
});

export async function readCiLogsHandler(args: z.infer<typeof ReadCiLogsInputSchema>) {
  const params = ["repo", "ci-logs", args.prNumber.toString()];
  if (args.all) {
    params.push("--all");
  }
  const output = await runTDCli(params);

  return {
    checks: output.checks,
    failedChecks: output.failedChecks,
    logs: output.logs
  };
}
