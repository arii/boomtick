import { z } from "zod";
import { JulesSession } from "../types.js";
import { runCommand } from "../../lib/shell.js";

export const CancelJulesSessionInputSchema = z.object({
  sessionId: z.string(),
});

export async function cancelJulesSessionHandler(input: z.infer<typeof CancelJulesSessionInputSchema>): Promise<JulesSession> {
  const result = await runCommand("td-cli", ["agent", "cancel", input.sessionId]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to cancel session: ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to cancel session: ${output.message}`);
  }

  return {
    id: input.sessionId.replace("sessions/", ""),
    status: "FAILED",
    createdAt: new Date(),
  };
}
