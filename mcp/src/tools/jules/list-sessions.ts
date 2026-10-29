import { z } from "zod";
import { JulesListSessionsInputSchema, JulesListSessionsResponse } from "../contract.js";
import { runTDCli } from "./cli.js";
import { parseJulesSession } from "./session.js";

export const ListJulesSessionsInputSchema = JulesListSessionsInputSchema;

export async function listJulesSessionsHandler(
  input: z.input<typeof ListJulesSessionsInputSchema>
): Promise<JulesListSessionsResponse> {
  const parsedInput = ListJulesSessionsInputSchema.parse(input);
  const output = await runTDCli(["agent", "sync"], "list sessions");
  const rawSessions = output.sessions || [];

  const sessions = rawSessions.map((session: any) => parseJulesSession(session));
  return { sessions };
}
