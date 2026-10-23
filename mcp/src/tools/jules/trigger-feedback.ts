import { z } from "zod";
import { runTDCli } from "./cli.js";

export const TriggerJulesFeedbackInputSchema = z.object({
  sessionId: z.string(),
});

export async function triggerJulesFeedbackHandler(input: z.infer<typeof TriggerJulesFeedbackInputSchema>) {
  return await runTDCli(["agent", "trigger-feedback", input.sessionId], "trigger feedback");
}
