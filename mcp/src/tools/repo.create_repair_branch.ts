import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { createWorktree, resolveRepoPath } from "../lib/git.js";
import { readAgentContractHandler } from "./repo.read_agent_contract.js";
import { ensureSharedDependencies } from "../lib/dependency_cache.js";

export const CreateRepairBranchInputSchema = z.object({
  prNumber: z.number(),
  repairBranchName: z.string().optional(),
  writeMode: z.boolean().optional().default(false),
  repo: z.string().optional().describe("Target repository override (e.g. org/repo or repo)."),
  path: z.string().optional().describe("Local filesystem path to target repository root."),
  repoPath: z.string().optional().describe("Alias for path to target repository root."),
});

export async function createRepairBranchHandler(args: z.infer<typeof CreateRepairBranchInputSchema>) {
  if (!args.writeMode) {
    throw new Error("writeMode must be true to create a repair branch.");
  }

  const targetCwd = resolveRepoPath({
    path: args.path,
    repoPath: args.repoPath,
    repo: args.repo,
  });

  const ghArgs = [
    "pr",
    "view",
    args.prNumber.toString(),
    "--json", "headRefName,baseRefName,title"
  ];
  if (args.repo) {
    ghArgs.push("--repo", args.repo);
  }

  const prResult = await runCommand("gh", ghArgs, { cwd: targetCwd });

  if (prResult.exitCode !== 0) {
    throw new Error(`Failed to get PR info: ${prResult.stderr}`);
  }

  const { headRefName, baseRefName, title } = JSON.parse(prResult.stdout);

  const sanitizedTitle = title.toLowerCase().replace(/[^a-z0-9]/g, "-").substring(0, 30);
  const repairBranch = args.repairBranchName || `agent/repair-pr-${args.prNumber}-${sanitizedTitle}`;

  // Ensure latest in target repo
  await runCommand("git", ["fetch", "origin", headRefName], { cwd: targetCwd });
  await runCommand("git", ["fetch", "origin", baseRefName], { cwd: targetCwd });
  const fetched = true;

  let baseSha: string | null = null;
  let prHeadSha: string | null = null;
  try {
    const baseShaRes = await runCommand("git", ["rev-parse", `origin/${baseRefName}`], { cwd: targetCwd });
    if (baseShaRes.exitCode === 0 && baseShaRes.stdout.trim()) {
      baseSha = baseShaRes.stdout.trim();
    }
  } catch {
    // Fallback if rev-parse fails
  }

  try {
    const headShaRes = await runCommand("git", ["rev-parse", `origin/${headRefName}`], { cwd: targetCwd });
    if (headShaRes.exitCode === 0 && headShaRes.stdout.trim()) {
      prHeadSha = headShaRes.stdout.trim();
    }
  } catch {
    // Fallback if rev-parse fails
  }

  const worktreePath = await createWorktree(`origin/${headRefName}`, args.prNumber, targetCwd);

  // Create the actual repair branch in the worktree
  await runCommand("git", ["checkout", "-b", repairBranch], { cwd: worktreePath });

  // Read agent contract to get dependency cache config and setup commands
  try {
    const contractResult = await readAgentContractHandler({ path: targetCwd });
    if (contractResult?.config) {
      await ensureSharedDependencies({
        repoPath: targetCwd,
        worktreePath,
        config: contractResult.config,
      });
    }
  } catch (e) {
    // Graceful fallback if agent contract is absent or dependency sharing fails
    console.warn("Could not apply agent contract dependency caching:", e);
  }

  const response: Record<string, unknown> = {
    prNumber: args.prNumber,
    originalBranch: headRefName,
    repairBranch,
    baseBranch: baseRefName,
    worktreePath,
    path: targetCwd,
    baseSha,
    prHeadSha,
    fetched,
  };

  if (args.repo) {
    response.repo = args.repo;
  }

  return response;
}
