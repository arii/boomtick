import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { config } from "../config.js";

export const CommitPatchInputSchema = z.object({
  worktreePath: z.string().optional(),
  message: z.string(),
  allowedFiles: z.array(z.string()),
  writeMode: z.boolean().optional().default(true),
});

export function parsePorcelainLine(line: string): string | null {
  if (!line || line.length < 3) return null;
  // Porcelain v1 lines start with two status characters followed by a space and filename
  // Examples: " M foo.ts", "M  foo.ts", "?? foo.ts", " A foo.ts"
  const match = line.match(/^..\s+(.*)$/);
  if (match) {
    let filePath = match[1].trim();
    // Handle quotes around filenames if present
    if (filePath.startsWith('"') && filePath.endsWith('"')) {
      filePath = filePath.slice(1, -1);
    }
    return filePath;
  }
  return null;
}

export async function commitPatchHandler(args: z.infer<typeof CommitPatchInputSchema>) {
  if (!args.writeMode) {
    throw new Error("writeMode must be true to commit changes.");
  }
  const worktreePath = args.worktreePath || config.repoPath;

  const statusResult = await runCommand("git", ["status", "--porcelain"], { cwd: worktreePath });
  const rawLines = statusResult.stdout.split("\n").filter(l => l.length > 0);
  const changedFiles = rawLines
    .map(parsePorcelainLine)
    .filter((f): f is string => f !== null && f.length > 0);

  const forbiddenFiles = changedFiles.filter(f => !args.allowedFiles.includes(f));
  if (forbiddenFiles.length > 0) {
    throw new Error(`The following files are not in the allowed list: ${forbiddenFiles.join(", ")}`);
  }

  if (changedFiles.length === 0) {
    throw new Error("No changes to commit.");
  }

  // Only stage allowed files rather than staging everything with 'git add .'
  await runCommand("git", ["add", "--", ...args.allowedFiles], { cwd: worktreePath });
  const commitResult = await runCommand("git", ["commit", "-m", args.message], { cwd: worktreePath });

  if (commitResult.exitCode !== 0) {
    throw new Error(`Failed to commit: ${commitResult.stderr}`);
  }

  const shaResult = await runCommand("git", ["rev-parse", "HEAD"], { cwd: worktreePath });

  return {
    success: true,
    commitSha: shaResult.stdout.trim(),
    changedFiles
  };
}
