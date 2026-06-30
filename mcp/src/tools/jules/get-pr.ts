import { z } from "zod";
import { runCommand } from "../../lib/shell.js";

export const GetJulesPullRequestInputSchema = z.object({
  id: z.string(),
});

export async function getJulesPullRequestHandler(input: z.infer<typeof GetJulesPullRequestInputSchema>) {
  const result = await runCommand("td-cli", ["agent", "get-session", input.id]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to get session: ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to get session: ${output.message}`);
  }

  const data = output.session;
  let pullRequestUrl: string | undefined;
  if (data.outputs && Array.isArray(data.outputs)) {
    for (const out of data.outputs) {
      if (out.pullRequest && out.pullRequest.url) {
        pullRequestUrl = out.pullRequest.url;
        break;
      }
    }
  }

  return {
    id: input.id.replace("sessions/", ""),
    pullRequestUrl,
  };
}
