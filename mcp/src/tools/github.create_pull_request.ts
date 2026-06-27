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
  const prArgs = [
    "pr",
    "create",
    "--base", args.base,
    "--head", args.head,
    "--title", args.title,
    "--body", args.body
  ];

  if (args.draft) {
    prArgs.push("--draft");
  }

  const result = await runCommand("gh", prArgs);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to create pull request: ${result.stderr}`);
  }

  return {
    success: true,
    url: result.stdout.trim()
  };
}
