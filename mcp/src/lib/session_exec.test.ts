import { describe, it, expect } from "vitest";
import fs from "fs/promises";
import os from "os";
import path from "path";
// NOTE (issue 1139, item 1): the worktree.* MCP tools were deleted with the
// orchestrator (`td worktree` / worktrees.py) owning lifecycle, including
// remove-side session abandonment (see test_remove_abandons_bound_sessions
// in cli/tests/test_td_worktree.py).
// NOTE (issue #1162): SessionManager.dispatch(), its singleton, the
// executor prompt copy, and all executor/session machinery were deleted;
// local_sessions.py is the single execution owner. Only the tool-receipt
// test below survives — dispatch/executor/prompt coverage was removed
// with the dead code it covered.

describe("mandatory tooling receipts (issue 1146)", () => {
  it("recordToolReceipt appends timestamped entries per worktree", async () => {
    const { recordToolReceipt } = await import("./session_manager.js");
    const dir = await fs.mkdtemp(path.join(os.tmpdir(), "receipt-"));
    recordToolReceipt(dir, "td.init_and_rag", { query: "x" });
    recordToolReceipt(dir, "td.verify_scope");
    const entries: Array<{ tool: string; timestamp: string }> = JSON.parse(
      await fs.readFile(path.join(dir, ".agent_tool_receipt.json"), "utf8"),
    );
    expect(entries.map((e) => e.tool)).toEqual(["td.init_and_rag", "td.verify_scope"]);
    expect(entries[0].timestamp).toBeTruthy();
    await fs.rm(dir, { recursive: true, force: true });
  });
});
