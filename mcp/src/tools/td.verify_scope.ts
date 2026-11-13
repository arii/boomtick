import { z } from "zod";
import { recordToolReceipt } from "../lib/session_manager.js";
import { runTDCli } from "../lib/tdCli.js";
import { TdVerifyScopeInputSchema } from "./contract.js";

export { TdVerifyScopeInputSchema };

export async function tdVerifyScopeHandler(args: z.infer<typeof TdVerifyScopeInputSchema>) {
  const params = TdVerifyScopeInputSchema.parse(args);
  const cliArgs = ["verify-scope", "--spec-file", params.specFile, "--worktree", params.worktree];
  if (params.autoRevert) {
    cliArgs.push("--auto-revert");
  }
  cliArgs.push("--json");
  const result = await runTDCli(cliArgs, "verify worktree scope");
  recordToolReceipt(params.worktree, "td.verify_scope");
  return result;
}
