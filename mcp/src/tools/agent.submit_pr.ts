import { z } from "zod";
import { AgentSubmitPrInputSchema } from "./contract.js";
import { readToolReceipts, resolveReceiptDir } from "../lib/session_manager.js";
import { emitToolTelemetry } from "../lib/tool_telemetry.js";
import { runTDCli } from "../lib/tdCli.js";

const RAG_TOOLS = new Set(["td.init_and_rag", "td.init", "td.rag", "repo.context"]);
const SCOPE_TOOLS = new Set(["td.verify_scope", "td.audit_worktree"]);

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
  const started = Date.now();
  const cwd = parsed.worktreePath ?? process.cwd();
  // Telemetry attributes to an explicit session locus only: with no
  // worktreePath the line would land in the server cwd as stray
  // clutter next to no receipts, so it is skipped (issue #1157).
  const done = (ok: boolean, detail?: string) => {
    if (parsed.worktreePath) {
      emitToolTelemetry(cwd, "agent.submit_pr", ok, Date.now() - started, detail);
    }
  };
  if (!parsed.pushMode) {
    done(false, "pushMode must be true");
    throw new Error("pushMode must be true to push and open the PR.");
  }
  // Reads go through the same receipt-dir resolution the td.* writers use —
  // separate fallbacks let receipts land in the server cwd while submission
  // looked in the worktree (audit H3).
  const receiptRead = readToolReceipts(resolveReceiptDir(parsed.worktreePath));
  if (receiptRead.error) {
    const detail =
      `tool receipt file is unreadable: ${receiptRead.error}. ` +
      "Repair or delete the file, then re-run td init (or repo read-agent-context).";
    done(false, detail);
    throw new Error(`PR submission blocked: ${detail}`);
  }
  const receipts = receiptRead.receipts;
  const receiptTools = receipts
    .map((r) => r.tool)
    .filter((tool): tool is string => typeof tool === "string");
  const usedRag = receiptTools.some((t) => RAG_TOOLS.has(t));
  const usedScope = receiptTools.some((t) => SCOPE_TOOLS.has(t));
  if (!usedRag || !usedScope) {
    const detail =
      `missing mandatory tool receipts (usedRag=${usedRag}, usedScope=${usedScope}). ` +
      "Run td init (or init-and-rag) or repo read-agent-context first, then td verify-scope and td audit-worktree.";
    done(false, detail);
    throw new Error(`PR submission blocked: ${detail}`);
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
  let res;
  try {
    res = await runTDCli(cliArgs, "submit PR via td agent submit-pr");
  } catch (err) {
    done(false, err instanceof Error ? err.message : String(err));
    throw err;
  }
  if (res.branch && res.branch !== parsed.branch) {
    done(false, `worktree is on ${res.branch}, request asked for ${parsed.branch}`);
    throw new Error(
      `Refusing to submit: worktree is on ${res.branch}, request asked for ${parsed.branch}.`,
    );
  }
  if (typeof res.url !== "string" || res.url.length === 0) {
    done(false, "td agent submit-pr returned no PR url");
    throw new Error("Submit failed: td agent submit-pr returned no PR url.");
  }
  done(true);
  return {
    status: "success",
    url: res.url,
    branch: res.branch ?? parsed.branch,
    baseBranch: res.base ?? parsed.baseBranch ?? "main",
    draft: res.draft ?? parsed.draft ?? true,
  };
}
