import { z } from "zod";
import { runTDCli } from "../../lib/td-cli.js";
import { parseJulesSession } from "./shared.js";

export const CreateJulesSessionInputSchema = z.object({
  task: z.string(),
  branch: z.string().optional(),
  pr: z.number().optional(),
});

export async function createJulesSessionHandler(input: z.infer<typeof CreateJulesSessionInputSchema>) {
  let branch = input.branch;
  if (!branch && input.pr) {
    const prData = await runTDCli(["gh", "view", input.pr.toString()]);
    branch = prData.pr.headRefName;
  }

  if (!branch) {
      branch = process.env.DEFAULT_BASE_BRANCH || "main";
  }

  const output = await runTDCli(["agent", "dispatch", branch, input.task]);
  return parseJulesSession(output.session || output);
}
