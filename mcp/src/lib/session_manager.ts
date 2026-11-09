import path from "path";
import * as syncFs from "fs";

// Issue #1162: SessionManager.dispatch() and its singleton were deleted.
// local_sessions.py (cli/dev_tools/services/local_sessions.py) is the single
// execution owner and the single source of the executor system prompt
// (build_system_prompt). Only the tool-receipt bookkeeping used by the
// td.* / repo.* / agent.submit_pr tools remains here.

export const RECEIPT_FILENAME = ".agent_tool_receipt.json";

// Bound receipt history so long-lived sessions cannot grow the file without bound.
export const MAX_TOOL_RECEIPTS = 500;
const RECEIPT_CAP_ENV_VAR = "BOOMTICK_RECEIPT_CAP";

function resolveReceiptCap(): number {
  const raw = process.env[RECEIPT_CAP_ENV_VAR];
  if (raw === undefined || raw.trim() === "") return MAX_TOOL_RECEIPTS;
  const parsed = Number(raw);
  if (!Number.isInteger(parsed) || parsed < 1) {
    console.warn(`Invalid ${RECEIPT_CAP_ENV_VAR} value "${raw}"; using default cap ${MAX_TOOL_RECEIPTS}.`);
    return MAX_TOOL_RECEIPTS;
  }
  return parsed;
}

export function recordToolReceipt(
  worktreePath: string,
  toolName: string,
  metadata: Record<string, unknown> = {},
): void {
  const receiptFile = path.join(worktreePath, RECEIPT_FILENAME);
  let existing: Array<Record<string, unknown>> = [];
  if (syncFs.existsSync(receiptFile)) {
    try {
      const parsed: unknown = JSON.parse(syncFs.readFileSync(receiptFile, "utf8"));
      if (Array.isArray(parsed)) {
        existing = parsed as Array<Record<string, unknown>>;
      }
    } catch {
      existing = [];
    }
  }
  existing.push({
    tool: toolName,
    timestamp: new Date().toISOString(),
    ...metadata,
  });
  const cap = resolveReceiptCap();
  const trimmed = existing.length > cap ? existing.slice(-cap) : existing;
  syncFs.writeFileSync(receiptFile, JSON.stringify(trimmed, null, 2), "utf8");
}
