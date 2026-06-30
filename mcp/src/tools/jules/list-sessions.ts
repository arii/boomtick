import { z } from "zod";
import { JulesSession, JulesStatus } from "../types.js";
import { runCommand } from "../../lib/shell.js";

export const ListJulesSessionsInputSchema = z.object({
  pageSize: z.number().optional(),
  pageToken: z.string().optional(),
});

export async function listJulesSessionsHandler(input: z.infer<typeof ListJulesSessionsInputSchema>): Promise<JulesSession[]> {
  const result = await runCommand("td-cli", ["agent", "sync"]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to list sessions: ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to list sessions: ${output.message}`);
  }

  const sessions = output.sessions || [];

  return sessions.map((session: any) => {
    const name = session.name || "";
    const id = name.startsWith("sessions/") ? name.substring(9) : name;

    let status: JulesStatus = "PENDING";
    if (session.state === "SUCCEEDED" || session.state === "COMPLETED") status = "COMPLETED";
    else if (session.state === "FAILED" || session.state === "CANCELLED" || session.state === "TERMINATED") status = "FAILED";
    else if (session.state === "IN_PROGRESS") status = "IN_PROGRESS";

    let pullRequestUrl: string | undefined;
    if (session.outputs && Array.isArray(session.outputs)) {
      for (const out of session.outputs) {
        if (out.pullRequest && out.pullRequest.url) {
          pullRequestUrl = out.pullRequest.url;
          break;
        }
      }
    }

    return {
      id,
      status,
      createdAt: session.createTime ? new Date(session.createTime) : new Date(),
      pullRequestUrl,
    };
  });
}
