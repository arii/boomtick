import { z } from "zod";
import { runTDCli } from "./cli.js";

export const GetJulesMessagesInputSchema = z.object({
  sessionId: z.string(),
});

export async function getJulesMessagesHandler(input: z.infer<typeof GetJulesMessagesInputSchema>) {
  const output = await runTDCli(["agent", "messages", input.sessionId], "get messages");

  return {
    id: input.sessionId.replace("sessions/", ""),
    messages: output.messages,
  };
}
