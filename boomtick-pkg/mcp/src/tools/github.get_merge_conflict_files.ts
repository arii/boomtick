import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const GetMergeConflictFilesInputSchema = z.object({
  prNumber: z.number(),
  baseBranch: z.string().optional().default("main"),
});

export async function getMergeConflictFilesHandler(args: z.infer<typeof GetMergeConflictFilesInputSchema>) {
  const result = await runCommand("td-cli", [
    "gh", "merge-conflicts", args.prNumber.toString(),
    "--base", args.baseBranch || "main"
  ]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to get merge conflicts: ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to get merge conflicts: ${output.message}`);
  }

  return {
    prNumber: output.prNumber,
    baseBranch: output.baseBranch,
    headRef: output.headRef,
    conflictFiles: output.conflictFiles,
    commandLog: output.commandLog
  };
}
