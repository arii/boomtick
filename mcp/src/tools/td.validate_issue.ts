import { z } from "zod";
import { runTDCli } from "../lib/tdCli.js";
import { TdValidateIssueInputSchema } from "./contract.js";

export { TdValidateIssueInputSchema };

export async function tdValidateIssueHandler(args: z.infer<typeof TdValidateIssueInputSchema>) {
  const params = TdValidateIssueInputSchema.parse(args);
  const cliArgs = ["validate-issue", "--file", params.file];
  if (params.repoRoot) {
    cliArgs.push("--repo-root", params.repoRoot);
  }
  cliArgs.push("--json");
  return runTDCli(cliArgs, "validate issue spec");
}
