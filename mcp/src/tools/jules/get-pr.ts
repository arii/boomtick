import { z } from "zod";
import { runTDCli } from "../../lib/td-cli.js";
import { parseJulesSession } from "./shared.js";

export const GetJulesPullRequestInputSchema = z.object({
  id: z.string(),
});

export async function getJulesPullRequestHandler(input: z.infer<typeof GetJulesPullRequestInputSchema>) {
  const output = await runTDCli(["agent", "get-session", input.id]);
  const session = parseJulesSession(output.session);

  return {
    id: session.id,
    pullRequestUrl: session.pullRequestUrl,
  };
}
