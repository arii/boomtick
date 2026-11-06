import * as fs from "node:fs";
import * as path from "node:path";
import { z } from "zod";
import { AgentSubmitPrInputSchema } from "./contract.js";
import { RECEIPT_FILENAME } from "../lib/session_manager.js";
import { runCommand } from "../lib/shell.js";

const RAG_TOOLS = new Set(["td.init_and_rag", "repo.read_agent_context"]);
const SCOPE_TOOLS = new Set(["td.verify_scope", "td.audit_worktree"]);

function readToolReceipts(worktreePath: string): Array<{ tool: string }> {
  const receiptPath = path.join(worktreePath, RECEIPT_FILENAME);
  if (!fs.existsSync(receiptPath)) {
    return [];
  }
  try {
    const parsed: unknown = JSON.parse(fs.readFileSync(receiptPath, "utf8"));
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

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
  const receipts = readToolReceipts(parsed.worktreePath ?? process.cwd());
  const usedRag = receipts.some((r) => RAG_TOOLS.has(r.tool));
  const usedScope = receipts.some((r) => SCOPE_TOOLS.has(r.tool));
  if (!usedRag || !usedScope) {
    throw new Error(
      `PR submission blocked: missing mandatory tool receipts (usedRag=${usedRag}, usedScope=${usedScope}). ` +
        "Run td init-and-rag or repo read-agent-context first, then td verify-scope and td audit-worktree.",
    );
  }
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
