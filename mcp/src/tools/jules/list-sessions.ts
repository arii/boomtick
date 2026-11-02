import { z } from "zod";
import { JulesListSessionsInputSchema, JulesListSessionsResponse } from "../contract.js";
import { runTDCli } from "./cli.js";
import { parseJulesSession } from "./session.js";
import { resolveStackEnvPath } from "../../config.js";

export const ListJulesSessionsInputSchema = JulesListSessionsInputSchema;

export async function listJulesSessionsHandler(
  input: z.input<typeof ListJulesSessionsInputSchema>
): Promise<JulesListSessionsResponse> {
  const parsedInput = ListJulesSessionsInputSchema.parse(input);
  const output = await runTDCli(["agent", "sync"], "list sessions");

  if (output?.warning && typeof output.warning === "string" && output.warning.includes("JULES_API_KEY unset")) {
    throw new Error(
      `JULES_API_KEY is not set or empty (checked in environment and ${resolveStackEnvPath()})`
    );
  }

  const rawSessions = output.sessions || [];

  const sessions = rawSessions.map((session: any) => parseJulesSession(session));
  return { sessions };
}
