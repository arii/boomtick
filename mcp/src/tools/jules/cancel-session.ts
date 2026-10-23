import { z } from "zod";
import { JulesSession } from "../types.js";
import { runTDCli } from "./cli.js";

export const CancelJulesSessionInputSchema = z.object({
  sessionId: z.string(),
});

export async function cancelJulesSessionHandler(input: z.infer<typeof CancelJulesSessionInputSchema>): Promise<JulesSession> {
  await runTDCli(["agent", "cancel", input.sessionId], "cancel session");

  return {
    id: input.sessionId.replace("sessions/", ""),
    status: "FAILED",
    createdAt: new Date(),
  };
}
