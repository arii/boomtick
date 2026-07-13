import { z } from "zod";
import { runCommand } from "../../lib/shell.js";

export const TriggerJulesFeedbackInputSchema = z.object({
  sessionId: z.string(),
});

export async function triggerJulesFeedbackHandler(input: z.infer<typeof TriggerJulesFeedbackInputSchema>) {
  const result = await runCommand("td-cli", ["agent", "trigger-feedback", input.sessionId]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to trigger feedback: ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to trigger feedback: ${output.message}`);
  }

  return output;
}
