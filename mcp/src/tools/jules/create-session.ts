import { z } from "zod";
import { JulesSession, JulesStatus } from "../types.js";
import { runCommand } from "../../lib/shell.js";

export const CreateJulesSessionInputSchema = z.object({
  task: z.string(),
  branch: z.string().optional(),
  pr: z.number().optional(),
});

export async function createJulesSessionHandler(input: z.infer<typeof CreateJulesSessionInputSchema>): Promise<JulesSession> {
  const args = ["agent", "dispatch"];

  let branch = input.branch;
  if (!branch && input.pr) {
    // If branch not provided but PR is, we need to get it.
    // td-cli agent dispatch requires a branch.
    const prResult = await runCommand("td-cli", ["gh", "view", input.pr.toString()]);
    if (prResult.exitCode === 0) {
       const prData = JSON.parse(prResult.stdout).pr;
       branch = prData.headRefName;
    }
  }

  if (!branch) {
      branch = process.env.DEFAULT_BASE_BRANCH || "main";
  }

  args.push(branch, input.task);

  const result = await runCommand("td-cli", args);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to create session: ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to create session: ${output.message}`);
  }

  const data = output.session || output;
  const name = data.name || "";
  const id = name.startsWith("sessions/") ? name.substring(9) : name;

  let status: JulesStatus = "PENDING";
  if (data.state === "SUCCEEDED" || data.state === "COMPLETED") status = "COMPLETED";
  else if (data.state === "FAILED" || data.state === "CANCELLED" || data.state === "TERMINATED") status = "FAILED";
  else if (data.state === "IN_PROGRESS") status = "IN_PROGRESS";

  return {
    id,
    status,
    createdAt: data.createTime ? new Date(data.createTime) : new Date(),
  };
}
