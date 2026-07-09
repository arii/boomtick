import { z } from "zod";
import { runCommand } from "../../lib/shell.js";

export const SendJulesMessageInputSchema = z.object({
  sessionId: z.union([z.string(), z.array(z.string())]),
  message: z.string(),
});

export async function sendJulesMessageHandler(input: z.infer<typeof SendJulesMessageInputSchema>) {
  const sessionIds = Array.isArray(input.sessionId) ? input.sessionId.join(",") : input.sessionId;
  const result = await runCommand("td-cli", ["agent", "send", sessionIds, input.message]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to send message: ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to send message: ${output.message}`);
  }

  return {
    id: Array.isArray(input.sessionId) ? input.sessionId.map(id => id.replace("sessions/", "")) : input.sessionId.replace("sessions/", ""),
    status: "success",
    message: "Message sent successfully",
  };
}
