import { z } from "zod";
import { runTDCli } from "../lib/tdCli.js";

export const TdAuditWorktreeInputSchema = z.object({
  worktree: z.string().describe("Path to the worktree to audit."),
  includeImpact: z.boolean().optional().describe("Also run blast-radius impact analysis (td audit-impact)."),
  topK: z.number().optional().describe("Maximum impacted files to list."),
});

export async function tdAuditWorktreeHandler(args: z.infer<typeof TdAuditWorktreeInputSchema>) {
  const params = TdAuditWorktreeInputSchema.parse(args);
  const audit = await runTDCli(["audit-code", "--worktree", params.worktree, "--json"], "audit worktree code");
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
