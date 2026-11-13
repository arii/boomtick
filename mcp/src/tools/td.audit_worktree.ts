import { z } from "zod";
import { recordToolReceipt } from "../lib/session_manager.js";
import { runTDCli } from "../lib/tdCli.js";
import { TdAuditWorktreeInputSchema } from "./contract.js";

export { TdAuditWorktreeInputSchema };

export async function tdAuditWorktreeHandler(args: z.infer<typeof TdAuditWorktreeInputSchema>) {
  const params = TdAuditWorktreeInputSchema.parse(args);
  const audit = await runTDCli(["audit-code", "--worktree", params.worktree, "--json"], "audit worktree code");
  recordToolReceipt(params.worktree, "td.audit_worktree");
  if (!params.includeImpact) {
    return audit;
  }
  const impactArgs = ["audit-impact", "--worktree", params.worktree];
  if (params.topK !== undefined) {
    impactArgs.push("--top-k", params.topK.toString());
  }
  impactArgs.push("--json");
  const impact = await runTDCli(impactArgs, "audit worktree impact");
  return { audit, impact };
}
