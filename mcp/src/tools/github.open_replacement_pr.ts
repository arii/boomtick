import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const OpenReplacementPrInputSchema = z.object({
  originalPrNumber: z.number(),
  repairBranch: z.string(),
  baseBranch: z.string(),
  title: z.string(),
  body: z.string(),
  draft: z.boolean().optional().default(true),
  worktreePath: z.string().optional(),
  pushMode: z.boolean().optional().default(false),
});

export async function openReplacementPrHandler(args: z.infer<typeof OpenReplacementPrInputSchema>) {
  if (!args.pushMode) {
    throw new Error("pushMode must be true to push and open a replacement PR.");
  }
  // Push the branch
  const pushResult = await runCommand("git", ["push", "origin", args.repairBranch], { cwd: args.worktreePath });
  if (pushResult.exitCode !== 0) {
    throw new Error(`Failed to push branch: ${pushResult.stderr}`);
  }

  const prArgs = [
    "pr",
    "create",
    "--base", args.baseBranch,
    "--head", args.repairBranch,
    "--title", args.title,
    "--body", args.body
  ];

  if (args.draft) {
    prArgs.push("--draft");
  }

  const result = await runCommand("gh", prArgs, { cwd: args.worktreePath });

  if (result.exitCode !== 0) {
    throw new Error(`Failed to open replacement PR: ${result.stderr}`);
  }

  return {
    success: true,
    url: result.stdout.trim()
  };
}
