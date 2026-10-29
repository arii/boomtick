import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { resolveRepoPath } from "../lib/git.js";

export const CreateBranchInputSchema = z.object({
  branchName: z.string(),
  baseBranch: z.string().optional().default("main"),
  repo: z.string().optional().describe("Target repository override (e.g. org/repo or repo)."),
  path: z.string().optional().describe("Local filesystem path to target repository root."),
  repoPath: z.string().optional().describe("Alias for path to target repository root."),
});

export type CreateBranchInput = z.input<typeof CreateBranchInputSchema>;

export async function createBranchHandler(args: CreateBranchInput) {
  const params = CreateBranchInputSchema.parse(args);
  const targetCwd = resolveRepoPath({
    path: params.path,
    repoPath: params.repoPath,
    repo: params.repo,
  });

  // Ensure latest base branch
  await runCommand("git", ["fetch", "origin", params.baseBranch], { cwd: targetCwd });

  // Create branch from origin base branch
  const result = await runCommand(
    "git",
    ["checkout", "-b", params.branchName, `origin/${params.baseBranch}`],
    { cwd: targetCwd }
  );

  if (result.exitCode !== 0) {
    throw new Error(`Failed to create branch ${params.branchName}: ${result.stderr}`);
  }

  const response: {
    success: boolean;
    branchName: string;
    baseBranch: string;
    path: string;
    repo?: string;
  } = {
    success: true,
    branchName: params.branchName,
    baseBranch: params.baseBranch,
    path: targetCwd,
  };

  if (params.repo) {
    response.repo = params.repo;
  }

  return response;
}
