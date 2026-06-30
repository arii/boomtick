import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const RepoLogsInputSchema = z.object({
  prNumber: z.number(),
  grep: z.string().optional(),
});

export async function repoLogsHandler(args: z.infer<typeof RepoLogsInputSchema>) {
  RepoLogsInputSchema.parse(args);
  const params = [
    "repo", "logs", args.prNumber.toString()
  ];

  if (args.grep) {
    params.push("--grep", args.grep);
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
    logs: output.logs || (output.data ? output.data.logs : undefined)
  };
}
