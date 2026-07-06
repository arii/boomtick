import { z } from "zod";
import { runCommand } from "../../lib/shell.js";

export const SendJulesMessageInputSchema = z.object({
  sessionId: z.string(),
  message: z.string(),
});

export async function sendJulesMessageHandler(input: z.infer<typeof SendJulesMessageInputSchema>) {
  const result = await runCommand("td-cli", ["agent", "send", input.sessionId, input.message]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to send message: ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to send message: ${output.message}`);
  }

  return {
    id: input.sessionId.replace("sessions/", ""),
    status: "success",
    message: "Message sent successfully",
  };
}
