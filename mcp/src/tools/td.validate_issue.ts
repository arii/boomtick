import { z } from "zod";
import { runTDCli } from "../lib/tdCli.js";

export const TdValidateIssueInputSchema = z.object({
  file: z.string().describe("Path to the design spec file (or - for stdin)."),
  repoRoot: z.string().optional().describe("Repo root for file existence checks (default: git root)."),
});

export async function tdValidateIssueHandler(args: z.infer<typeof TdValidateIssueInputSchema>) {
  const params = TdValidateIssueInputSchema.parse(args);
  const cliArgs = ["validate-issue", "--file", params.file];
  if (params.repoRoot) {
    cliArgs.push("--repo-root", params.repoRoot);
  }
  cliArgs.push("--json");
  return runTDCli(cliArgs, "validate issue spec");
}
