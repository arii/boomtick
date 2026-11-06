import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import fs from "fs/promises";
import os from "os";
import path from "path";
import { execSync } from "child_process";
import { config } from "../config.js";
import { SessionManager } from "./session_manager.js";
import {
  EXECUTOR_PROMPT_TEMPLATE,
  fillExecutorPrompt,
} from "./executor_prompt.js";
import { worktreeCreateHandler } from "../tools/worktree.create.js";
import { worktreeRemoveHandler } from "../tools/worktree.remove.js";

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

describe("worktree remove ends sessions (#1099)", () => {
  let tmpRepoDir: string;

  beforeEach(async () => {
    SessionManager.resetInstance();
    tmpRepoDir = await fs.mkdtemp(path.join(os.tmpdir(), "bt-wt-"));
    execSync("git init -b main", { cwd: tmpRepoDir });
    execSync('git config user.email "test@example.com"', { cwd: tmpRepoDir });
    execSync('git config user.name "Test Runner"', { cwd: tmpRepoDir });
    await fs.writeFile(path.join(tmpRepoDir, "README.md"), "# test\n");
    execSync("git add README.md && git commit -m init", { cwd: tmpRepoDir });
    vi.spyOn(config, "repoPath", "get").mockReturnValue(tmpRepoDir);
  });

  afterEach(async () => {
    vi.restoreAllMocks();
    SessionManager.resetInstance();
    try {
      await fs.rm(tmpRepoDir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  });

  it("remove abandons the bound session and reports it", async () => {
    const created = await worktreeCreateHandler({
      name: "Wt Test",
      baseBranch: "main",
      writeMode: true,
      repo: null,
      path: null,
    } as any);
    const mgr = SessionManager.getInstance();
    mgr.registerSession(fakeSession({
      sessionId: "sess_bound",
      worktreeId: created.worktreeId,
      worktreePath: created.path,
    }));
    const removed = await worktreeRemoveHandler({
      worktreeId: created.worktreeId,
      force: false,
      writeMode: true,
      repo: null,
      path: null,
    } as any);
    expect(removed.status).toBe("removed");
    expect(removed.abandonedSessions).toContain("sess_bound");
    expect(mgr.getSession("sess_bound").state).toBe("abandoned");
  });
});
