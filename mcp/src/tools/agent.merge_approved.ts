import { z } from "zod";
import { AgentMergeApprovedInputSchema, AgentMergeApprovedResponse } from "./contract.js";
import { runTDCli } from "./jules/cli.js";

export async function agentMergeApprovedHandler(
  input: z.input<typeof AgentMergeApprovedInputSchema>
): Promise<AgentMergeApprovedResponse> {
  const parsed = AgentMergeApprovedInputSchema.parse(input);
  const args = ["agent", "merge-approved"];

  if (parsed.repo) {
    args.push("-r", parsed.repo);
  }

  if (parsed.execute) {
    args.push("--execute");
  } else {
    args.push("--dry-run");
  }

  const res = await runTDCli(args, "agent merge-approved");
  return res as unknown as AgentMergeApprovedResponse;
}
