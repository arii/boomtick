import path from "path";
import * as syncFs from "fs";

// Issue #1162: SessionManager.dispatch() and its singleton were deleted.
// local_sessions.py (cli/dev_tools/services/local_sessions.py) is the single
// execution owner and the single source of the executor system prompt
// (build_system_prompt). Only the tool-receipt bookkeeping used by the
// td.* / repo.* / agent.submit_pr tools remains here.

export const RECEIPT_FILENAME = ".agent_tool_receipt.json";

/**
 * Single source of truth for which directory holds a session's tool receipts.
 * Writers (td.init, td.rag, td.verify_scope, td.audit_worktree) and readers
 * (agent.submit_pr) must both go through this helper — with separate
 * `?? process.cwd()` fallbacks on each side, receipts recorded for one root
 * were read from another (audit hypothesis H3).
 */
export function resolveReceiptDir(explicitRoot?: string | null): string {
  return explicitRoot ? path.resolve(explicitRoot) : process.cwd();
}

/**
 * Read a directory's tool receipts. A missing file is the normal
 * no-receipts-yet state; a file that exists but cannot be parsed is a
 * distinct, surfaced error — swallowing it to [] made a corrupt receipt
 * file indistinguishable from "agent never ran the required tools".
 */
export interface ReceiptReadResult {
  receipts: Array<Record<string, unknown>>;
  /** Set when the receipt file exists but could not be parsed. */
  error?: string;
}

export function readToolReceipts(dir: string): ReceiptReadResult {
  const receiptFile = path.join(dir, RECEIPT_FILENAME);
  if (!syncFs.existsSync(receiptFile)) {
    return { receipts: [] };
  }
  try {
    const parsed: unknown = JSON.parse(syncFs.readFileSync(receiptFile, "utf8"));
    if (Array.isArray(parsed)) {
      return { receipts: parsed as Array<Record<string, unknown>> };
    }
    return {
      receipts: [],
      error: `${receiptFile} is not a JSON array (found ${typeof parsed})`,
    };
  } catch (err) {
    return {
      receipts: [],
      error: `failed to parse ${receiptFile}: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}

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
  const read = readToolReceipts(worktreePath);
  if (read.error) {
    // Surface the corruption loudly, but don't break the tool that just ran —
    // the next reader will also refuse the file and report it.
    console.warn(`tool receipt file unreadable; starting a fresh history. ${read.error}`);
  } else {
    existing = read.receipts;
  }
  existing.push({
    tool: toolName,
    timestamp: new Date().toISOString(),
    ...metadata,
  });
  const cap = resolveReceiptCap();
  const trimmed = existing.length > cap ? existing.slice(-cap) : existing;
  // Atomic write via temp file + rename: a concurrent reader (agent.submit_pr)
  // never observes a partially written receipt file, and a crashed write never
  // truncates the existing history.
  const tmpFile = path.join(worktreePath, `${RECEIPT_FILENAME}.${process.pid}.tmp`);
  try {
    syncFs.writeFileSync(tmpFile, JSON.stringify(trimmed, null, 2), "utf8");
    syncFs.renameSync(tmpFile, receiptFile);
  } catch (err) {
    try {
      syncFs.unlinkSync(tmpFile);
    } catch {
      // nothing to clean up; the original error is the one that matters
    }
    throw err;
  }
}
