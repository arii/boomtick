import { z } from "zod";
import { runTDCli } from "../lib/td-cli.js";

export const ReadCiLogsInputSchema = z.object({
  prNumber: z.number(),
  all: z.boolean().optional(),
  repo: z.string().optional(),
});

export async function readCiLogsHandler(args: z.infer<typeof ReadCiLogsInputSchema>) {
  const params = ["repo", "ci-logs", args.prNumber.toString()];
  if (args.all) {
    params.push("--all");
  }
  if (args.repo) {
    params.push("--repo", args.repo);
  }
  const output = await runTDCli(params);

  return {
    checks: output.checks,
    failedChecks: output.failedChecks,
    logs: output.logs
  };
}
