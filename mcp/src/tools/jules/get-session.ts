import { z } from "zod";
import { JulesSession, JulesStatus } from "../types.js";
import { runCommand } from "../../lib/shell.js";

export const GetJulesSessionInputSchema = z.object({
  id: z.string(),
});

export async function getJulesSessionHandler(input: z.infer<typeof GetJulesSessionInputSchema>): Promise<JulesSession> {
  const result = await runCommand("td-cli", ["agent", "get-session", input.id]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to get session: ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to get session: ${output.message}`);
  }

  const data = output.session;
  const name = data.name || "";
  const id = name.startsWith("sessions/") ? name.substring(9) : name;

  let status: JulesStatus = "PENDING";
  if (data.state === "SUCCEEDED" || data.state === "COMPLETED") status = "COMPLETED";
  else if (data.state === "FAILED" || data.state === "CANCELLED" || data.state === "TERMINATED") status = "FAILED";
  else if (data.state === "IN_PROGRESS") status = "IN_PROGRESS";

  let pullRequestUrl: string | undefined;
  if (data.outputs && Array.isArray(data.outputs)) {
    for (const out of data.outputs) {
      if (out.pullRequest && out.pullRequest.url) {
        pullRequestUrl = out.pullRequest.url;
        break;
      }
    }
  }

  return {
    id,
    status,
    createdAt: data.createTime ? new Date(data.createTime) : new Date(),
    pullRequestUrl,
  };
}
