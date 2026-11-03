import { z } from "zod";
import { AgentSubmitPrInputSchema } from "./contract.js";
import { runCommand } from "../lib/shell.js";

/**
 * Submit a branch as a pull request (push + open). Agents submit;
 * humans merge. There is intentionally no merge authority here:
 * human merging stays in `td agent merge-approved --execute`.
 */
export async function agentSubmitPrHandler(
  input: z.input<typeof AgentSubmitPrInputSchema>
): Promise<{
  status: string;
  url: string;
  branch: string;
  baseBranch: string;
  draft: boolean;
}> {
  const parsed = AgentSubmitPrInputSchema.parse(input);
  if (!parsed.pushMode) {
    throw new Error("pushMode must be true to push and open the PR.");
  }
  const cwd = parsed.worktreePath ?? undefined;
  const pushRes = await runCommand("git", ["push", "origin", parsed.branch], { cwd });
  if (pushRes.exitCode !== 0) {
    throw new Error(`Failed to push branch ${parsed.branch}: ${pushRes.stderr || pushRes.stdout}`);
  }
  const prArgs = [
    "pr", "create",
    "--base", parsed.baseBranch,
    "--head", parsed.branch,
    "--title", parsed.title,
    "--body", parsed.body,
  ];
  if (parsed.draft) {
    prArgs.push("--draft");
  }
  if (parsed.repo) {
    prArgs.push("--repo", parsed.repo);
  }
  const prRes = await runCommand("gh", prArgs, { cwd });
  if (prRes.exitCode !== 0) {
    throw new Error(`Failed to open PR: ${prRes.stderr || prRes.stdout}`);
  }
  return {
    status: "success",
    url: prRes.stdout.trim(),
    branch: parsed.branch,
    baseBranch: parsed.baseBranch,
    draft: parsed.draft,
  };
}
