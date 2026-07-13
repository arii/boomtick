import { z } from "zod";
import { runTDCli } from "../lib/td-cli.js";

export const RepoLogsInputSchema = z.object({
  prNumber: z.number(),
  grep: z.string().optional(),
});

export async function repoLogsHandler(args: z.infer<typeof RepoLogsInputSchema>) {
  const params = ["repo", "logs", args.prNumber.toString()];

  if (args.grep) {
    params.push("--grep", args.grep);
  }

  const output = await runTDCli(params);

  return {
    logs: output.logs || (output.data ? output.data.logs : undefined)
  };
}
