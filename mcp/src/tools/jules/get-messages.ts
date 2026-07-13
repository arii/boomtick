import { z } from "zod";
import { runCommand } from "../../lib/shell.js";

export const GetJulesMessagesInputSchema = z.object({
  sessionId: z.string(),
});

export async function getJulesMessagesHandler(input: z.infer<typeof GetJulesMessagesInputSchema>) {
  const result = await runCommand("td-cli", ["agent", "messages", input.sessionId]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to get messages: ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to get messages: ${output.message}`);
  }

  return {
    id: input.sessionId.replace("sessions/", ""),
    messages: output.messages,
  };
}
