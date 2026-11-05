import { z } from "zod";
import { runTDCli } from "../lib/tdCli.js";

export const TdVerifyScopeInputSchema = z.object({
  specFile: z.string().describe("Path to the validated design spec markdown file."),
  worktree: z.string().describe("Path to the worktree to gate."),
  autoRevert: z.boolean().optional().describe("Revert files outside the allowed scope."),
});

export async function tdVerifyScopeHandler(args: z.infer<typeof TdVerifyScopeInputSchema>) {
  const params = TdVerifyScopeInputSchema.parse(args);
  const cliArgs = ["verify-scope", "--spec-file", params.specFile, "--worktree", params.worktree];
  if (params.autoRevert) {
    cliArgs.push("--auto-revert");
  }
  cliArgs.push("--json");
  return runTDCli(cliArgs, "verify worktree scope");
}
