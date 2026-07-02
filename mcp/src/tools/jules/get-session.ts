import { z } from "zod";
import { runTDCli } from "../../lib/td-cli.js";
import { parseJulesSession } from "./shared.js";

export const GetJulesSessionInputSchema = z.object({
  id: z.string(),
});

export async function getJulesSessionHandler(input: z.infer<typeof GetJulesSessionInputSchema>) {
  const output = await runTDCli(["agent", "get-session", input.id]);
  return parseJulesSession(output.session);
}
