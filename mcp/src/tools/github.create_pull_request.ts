import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const CreatePullRequestInputSchema = z.object({
  title: z.string(),
  body: z.string(),
  head: z.string(),
  base: z.string().optional().default("main"),
  draft: z.boolean().optional().default(false),
});

export async function createPullRequestHandler(args: z.infer<typeof CreatePullRequestInputSchema>) {
  const tdArgs = [
    "gh",
    "create-pr",
    "--title", args.title,
    "--body", args.body,
    "--head", args.head,
    "--base", args.base
  ];

  if (args.draft) {
    tdArgs.push("--draft");
  }

  const result = await runCommand("td-cli", tdArgs);

  if (result.exitCode !== 0) {
    // Attempt to parse stdout as JSON to see if there's a structured error message
    try {
      const errorOutput = JSON.parse(result.stdout);
      if (errorOutput.status === "error") {
        throw new Error(`Failed to create pull request: ${errorOutput.message}`);
      }
    } catch (e) {
      // If parsing fails, fall back to stderr or a generic message
    }
    throw new Error(`Failed to create pull request: ${result.stderr || result.stdout || "Unknown error"}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to create pull request: ${output.message}`);
  }

  return {
    success: true,
    url: output.pr.html_url
  };
}
