import { z } from "zod";
import { runTDCli } from "./cli.js";

export const SendJulesMessageInputSchema = z.object({
  sessionId: z.union([z.string(), z.array(z.string())]),
  message: z.string(),
});

export async function sendJulesMessageHandler(input: z.infer<typeof SendJulesMessageInputSchema>) {
  const sessionIds = Array.isArray(input.sessionId) ? input.sessionId.join(",") : input.sessionId;
  await runTDCli(["agent", "send", sessionIds, input.message], "send message");

  return {
    id: Array.isArray(input.sessionId) ? input.sessionId.map(id => id.replace("sessions/", "")) : input.sessionId.replace("sessions/", ""),
    status: "success",
    message: "Message sent successfully",
  };
}
