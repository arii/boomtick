import { z } from "zod";
import { JulesListSessionsResponse } from "../contract.js";
import { runTDCli } from "./cli.js";
import { parseJulesSession } from "./session.js";

export const ListJulesSessionsInputSchema = z.object({
  pageSize: z.number().optional(),
  pageToken: z.string().optional(),
});

export async function listJulesSessionsHandler(input: z.infer<typeof ListJulesSessionsInputSchema>): Promise<JulesListSessionsResponse> {
  const output = await runTDCli(["agent", "sync"], "list sessions");
  const rawSessions = output.sessions || [];
  const sessions = rawSessions.map((session: any) => parseJulesSession(session));

  return { sessions };
}
