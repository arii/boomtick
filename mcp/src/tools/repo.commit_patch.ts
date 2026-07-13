import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const CommitPatchInputSchema = z.object({
  worktreePath: z.string(),
  message: z.string(),
  allowedFiles: z.array(z.string()),
  writeMode: z.boolean().optional().default(false),
});

export async function commitPatchHandler(args: z.infer<typeof CommitPatchInputSchema>) {
  if (!args.writeMode) {
    throw new Error("writeMode must be true to commit changes.");
  }
  const statusResult = await runCommand("git", ["status", "--porcelain"], { cwd: args.worktreePath });
  const changedFiles = statusResult.stdout.trim().split("\n").filter(l => l.length > 0).map(l => l.substring(3));

  const forbiddenFiles = changedFiles.filter(f => !args.allowedFiles.includes(f));
  if (forbiddenFiles.length > 0) {
    throw new Error(`The following files are not in the allowed list: ${forbiddenFiles.join(", ")}`);
  }

  if (changedFiles.length === 0) {
    throw new Error("No changes to commit.");
  }

  await runCommand("git", ["add", "."], { cwd: args.worktreePath });
  const commitResult = await runCommand("git", ["commit", "-m", args.message], { cwd: args.worktreePath });

  if (commitResult.exitCode !== 0) {
    throw new Error(`Failed to commit: ${commitResult.stderr}`);
  }

  const shaResult = await runCommand("git", ["rev-parse", "HEAD"], { cwd: args.worktreePath });

  return {
    success: true,
    commitSha: shaResult.stdout.trim(),
    changedFiles
  };
}
