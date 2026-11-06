import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import fs from "fs/promises";
import os from "os";
import path from "path";
import { SessionManager } from "./session_manager.js";
import {
  EXECUTOR_PROMPT_TEMPLATE,
  fillExecutorPrompt,
} from "./executor_prompt.js";
// NOTE (#1139 item 1): the worktree.* MCP tools were deleted with the
// orchestrator (`td worktree` / worktrees.py) owning lifecycle, including
// remove-side session abandonment (see test_remove_abandons_bound_sessions
// in cli/tests/test_td_worktree.py).

function fakeSession(over: Record<string, unknown> = {}) {
  return {
    sessionId: "sess_test",
    worktreeId: "wt-test",
    worktreePath: "/tmp/bt-wt-test",
    branch: "wt-test",
    baseBranch: "main",
    repo: "arii/boomtick",
    brief: "do the thing",
    proposal: null,
    dispatcher: null,
    model: null,
    state: "running",
    createdAt: 1,
    updatedAt: 1,
    retries: 0,
    maxRetries: 3,
    transcript: [],
    logs: [],
    lastVerification: null,
    ...over,
  } as any;
}

describe("session machinery confinement (#1099, #1112)", () => {
  beforeEach(() => {
    SessionManager.resetInstance();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    SessionManager.resetInstance();
  });

  it("dispatch refuses when BOOMTICK_SESSION_EXEC=0", async () => {
    vi.stubEnv("BOOMTICK_SESSION_EXEC", "0");
    const mgr = SessionManager.getInstance();
    await expect(
      mgr.dispatch({ worktreeId: "wt-x", brief: "b", repo: null }),
    ).rejects.toThrow(/BOOMTICK_SESSION_EXEC=0/);
    expect(mgr.hasSession("sess_x")).toBe(false);
  });

  it("executor prompt fills every placeholder, none left over", async () => {
    const mgr = SessionManager.getInstance();
    const prompt = await mgr.buildExecutorPrompt(fakeSession({
      proposal: "the plan",
      dispatcher: "lane-coder",
    }));
    expect(prompt).not.toMatch(/\{\{[A-Z_]+\}\}/);
    expect(prompt).toContain("the plan");
    expect(prompt).toContain("lane-coder");
    expect(prompt).toContain("/tmp/bt-wt-test");
  });

  it("prompt falls back to brief and session id without guessing", async () => {
    const mgr = SessionManager.getInstance();
    const prompt = await mgr.buildExecutorPrompt(fakeSession());
    expect(prompt).toContain("Approved proposal: do the thing");
    expect(prompt).toContain("Report back to: session:sess_test");
    expect(prompt).not.toMatch(/\{\{[A-Z_]+\}\}/);
  });

  it("fillExecutorPrompt throws on unfilled placeholders", () => {
    expect(() =>
      fillExecutorPrompt("hi {{NOPE}}", {
        repo: "r", worktreePath: "w", branch: "b", baseBranch: "m",
        agentContract: "c", proposal: "p", taskBrief: "t", dispatcher: "d",
      }),
    ).toThrow(/NOPE/);
    expect(EXECUTOR_PROMPT_TEMPLATE).toContain("{{TASK_BRIEF}}");
  });

  it("executor env is an allowlist with pinned session root", () => {
    vi.stubEnv("PATH", "/usr/bin");
    vi.stubEnv("BOOMTICK_EXECUTOR_MODEL", "m");
    vi.stubEnv("NEBIUS_API_KEY", "secret");
    vi.stubEnv("FAKE_SECRET", "leak");
    vi.stubEnv("HOME", "/root");
    const mgr = SessionManager.getInstance();
    const env = mgr.buildExecutorEnv(fakeSession());
    expect(env.BOOMTICK_SESSION_ROOT).toBe("/tmp/bt-wt-test");
    expect(env.BOOMTICK_SESSION_ID).toBe("sess_test");
    expect(env.NEBIUS_API_KEY).toBe("secret");
    expect(env.BOOMTICK_EXECUTOR_MODEL).toBe("m");
    expect(env.FAKE_SECRET).toBeUndefined();
  });

  it("abandonSessionsInWorktree ends bound sessions only", async () => {
    const mgr = SessionManager.getInstance();
    mgr.registerSession(fakeSession({ sessionId: "s1" }));
    mgr.registerSession(fakeSession({
      sessionId: "s2", worktreePath: "/elsewhere", state: "running",
    }));
    mgr.registerSession(fakeSession({ sessionId: "s3", state: "done" }));
    const out = await mgr.abandonSessionsInWorktree("/tmp/bt-wt-test");
    expect(out).toEqual(["s1"]);
    expect(mgr.getSession("s1").state).toBe("abandoned");
    expect(mgr.getSession("s2").state).toBe("running");
  });
});

describe("mandatory tooling receipts (#1146)", () => {
  it("prepends the low-token protocol to the executor prompt", async () => {
    const mgr = SessionManager.getInstance();
    const prompt = await mgr.buildExecutorPrompt(fakeSession());
    expect(prompt.startsWith("[MANDATORY LOW-TOKEN PROTOCOL FOR CLI AGENTS]")).toBe(true);
    expect(prompt).toContain("td init-and-rag");
    expect(prompt).toContain("td verify-scope");
  });

  it("recordToolReceipt appends timestamped entries per worktree", async () => {
    const { recordToolReceipt } = await import("./session_manager.js");
    const dir = await fs.mkdtemp(path.join(os.tmpdir(), "receipt-"));
    recordToolReceipt(dir, "td.init_and_rag", { query: "x" });
    recordToolReceipt(dir, "td.verify_scope");
    const entries = JSON.parse(await fs.readFile(path.join(dir, ".agent_tool_receipt.json"), "utf8"));
    expect(entries.map((e: any) => e.tool)).toEqual(["td.init_and_rag", "td.verify_scope"]);
    expect(entries[0].timestamp).toBeTruthy();
    await fs.rm(dir, { recursive: true, force: true });
  });
});
