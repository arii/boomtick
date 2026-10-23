import { z } from "zod";
import { JulesSession } from "../types.js";
import { runTDCli } from "./cli.js";
import { parseJulesSession } from "./session.js";

export const ListJulesSessionsInputSchema = z.object({
  pageSize: z.number().optional(),
  pageToken: z.string().optional(),
});

export async function listJulesSessionsHandler(input: z.infer<typeof ListJulesSessionsInputSchema>): Promise<JulesSession[]> {
  const output = await runTDCli(["agent", "sync"], "list sessions");
  const sessions = output.sessions || [];

  return sessions.map((session: any) => parseJulesSession(session));
}
