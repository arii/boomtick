import * as fs from "node:fs";
import * as path from "node:path";
import { z } from "zod";
import { AgentSubmitPrInputSchema } from "./contract.js";
import { RECEIPT_FILENAME } from "../lib/session_manager.js";
import { runTDCli } from "../lib/tdCli.js";

const RAG_TOOLS = new Set(["td.init_and_rag", "td.init", "td.rag", "repo.read_agent_context"]);
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
 * Submit a branch as a pull request (push + open, draft by default). Agents submit;
 * humans merge. There is intentionally no merge authority here:
 * human merging stays in `td agent merge-approved --execute`.
 *
 * Deterministic CLI exit node (#1139 item 1): the push + PR open runs
 * through `td agent submit-pr`, not through inline git/gh calls. This
 * handler keeps the MCP-side submission policy (pushMode safety gate +
 * mandatory RAG/scope tool receipts) and maps the CLI result back.
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
  const cwd = parsed.worktreePath ?? process.cwd();
  const receipts = readToolReceipts(parsed.worktreePath ?? process.cwd());
  const usedRag = receipts.some((r) => RAG_TOOLS.has(r.tool));
  const usedScope = receipts.some((r) => SCOPE_TOOLS.has(r.tool));
  if (!usedRag || !usedScope) {
    throw new Error(
      `PR submission blocked: missing mandatory tool receipts (usedRag=${usedRag}, usedScope=${usedScope}). ` +
        "Run td init (or init-and-rag) or repo read-agent-context first, then td verify-scope and td audit-worktree.",
    );
  }
  const cliArgs = [
    "agent",
    "submit-pr",
    "--worktree",
    cwd,
    "--title",
    parsed.title,
    "--body",
    parsed.body ?? "",
    "--base",
    parsed.baseBranch ?? "main",
  ];
  if (parsed.repo) {
    cliArgs.push("--repo", parsed.repo);
  }
  if (parsed.draft === false) {
    cliArgs.push("--no-draft");
  }
  cliArgs.push("--json");
  const res = await runTDCli(cliArgs, "submit PR via td agent submit-pr");
  if (res.branch && res.branch !== parsed.branch) {
    throw new Error(
      `Refusing to submit: worktree is on ${res.branch}, request asked for ${parsed.branch}.`,
    );
  }
  return {
    status: "success",
    url: res.url,
    branch: res.branch ?? parsed.branch,
    baseBranch: res.base ?? parsed.baseBranch ?? "main",
    draft: res.draft ?? parsed.draft ?? true,
  };
}
