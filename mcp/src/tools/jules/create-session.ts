import { z } from "zod";
import { runTDCli, parseJulesSession } from "./shared.js";

export const CreateJulesSessionInputSchema = z.object({
  task: z.string(),
  branch: z.string().optional(),
  pr: z.number().optional(),
  repo: z.string().optional(),
});

export async function createJulesSessionHandler(input: z.infer<typeof CreateJulesSessionInputSchema>) {
  let branch = input.branch;
  if (!branch && input.pr) {
    const ghArgs = ["gh", "view", input.pr.toString()];
    if (input.repo) {
      ghArgs.push("--repo", input.repo);
    }
    const prData = await runTDCli(ghArgs);
    branch = prData.pr.headRefName;
  }

  if (!branch) {
      branch = process.env.DEFAULT_BASE_BRANCH || "main";
  }

  const dispatchArgs = ["agent", "dispatch"];
  if (input.repo) {
    dispatchArgs.push("--repo", input.repo);
  }
  dispatchArgs.push(branch, input.task);

  const output = await runTDCli(dispatchArgs);
  return parseJulesSession(output.session || output);
}
