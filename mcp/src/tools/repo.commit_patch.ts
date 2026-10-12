import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { config } from "../config.js";

export const CommitPatchInputSchema = z.object({
  worktreePath: z.string().optional(),
  message: z.string(),
  allowedFiles: z.array(z.string()),
  writeMode: z.boolean().optional().default(true),
});

export type CommitPatchInput = z.input<typeof CommitPatchInputSchema>;

export async function commitPatchHandler(args: CommitPatchInput) {
  const parsed = CommitPatchInputSchema.parse(args || {});
  const worktreePath = parsed.worktreePath || config.repoPath;

  if (parsed.writeMode === false) {
    throw new Error("writeMode must be true to commit changes.");
  }

  const statusResult = await runCommand("git", ["status", "--porcelain"], { cwd: worktreePath });

  const changedFiles = statusResult.stdout
    .split("\n")
    .map((l) => (l.endsWith("\r") ? l.slice(0, -1) : l))
    .filter((l) => l.trim().length > 0)
    .map((l) => {
      const match = l.match(/^..\s+(.*)$/);
      if (!match) return l.slice(3).trim();
      let file = match[1].trim();
      if (file.includes(" -> ")) {
        file = file.split(" -> ").pop()!.trim();
      }
      if (file.startsWith('"') && file.endsWith('"')) {
        file = file.slice(1, -1);
      }
      return file;
    })
    .filter(Boolean);

  const forbiddenFiles = changedFiles.filter((f) => !parsed.allowedFiles.includes(f));
  if (forbiddenFiles.length > 0) {
    throw new Error(`The following files are not in the allowed list: ${forbiddenFiles.join(", ")}`);
  }

  if (changedFiles.length === 0) {
    throw new Error("No changes to commit.");
  }

  await runCommand("git", ["add", "--", ...changedFiles], { cwd: worktreePath });
  const commitResult = await runCommand("git", ["commit", "-m", parsed.message], { cwd: worktreePath });

  if (commitResult.exitCode !== 0) {
    throw new Error(`Failed to commit: ${commitResult.stderr}`);
  }

  const shaResult = await runCommand("git", ["rev-parse", "HEAD"], { cwd: worktreePath });

  return {
    success: true,
    commitSha: shaResult.stdout.trim(),
    changedFiles,
  };
}
