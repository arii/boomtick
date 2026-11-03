import { describe, it, expect, beforeEach, afterEach } from "vitest";
import fs from "fs/promises";
import * as syncFs from "fs";
import path from "path";
import os from "os";
import { SessionManager } from "../lib/session_manager.js";
import { agentDispatchHandler } from "./agent.dispatch.js";
import { agentStatusHandler } from "./agent.status.js";
import { agentLogsHandler } from "./agent.logs.js";

describe("agent_dispatch with worktree-scoped sessions", () => {
  let tmpRepoDir: string;
  let tmpWorktreeDir: string;
  const worktreeId = "test-wt-1";

  beforeEach(async () => {
    tmpRepoDir = await fs.mkdtemp(path.join(os.tmpdir(), "bt-repo-"));
    const worktreesRoot = path.join(tmpRepoDir, ".worktrees");
    tmpWorktreeDir = path.join(worktreesRoot, worktreeId);
    await fs.mkdir(tmpWorktreeDir, { recursive: true });

    // Create a local AGENT_CONTRACT.md in worktree
    const agentsDir = path.join(tmpWorktreeDir, ".agents");
    await fs.mkdir(agentsDir, { recursive: true });
    await fs.writeFile(
      path.join(agentsDir, "AGENT_CONTRACT.md"),
      `# Test Worktree Contract\ntestCommand: echo "Tests passed"\nlintCommand: echo "Lint passed"\n`
    );

    // Initialize git repo in worktree
    await fs.writeFile(path.join(tmpWorktreeDir, "test.txt"), "hello world\n");
    const { execSync } = await import("child_process");
    execSync("git init -b main", { cwd: tmpWorktreeDir });
    execSync('git config user.email "test@example.com"', { cwd: tmpWorktreeDir });
    execSync('git config user.name "Test Runner"', { cwd: tmpWorktreeDir });
    execSync("git add . && git commit -m 'initial'", { cwd: tmpWorktreeDir });

    SessionManager.getInstance().reset();
    process.env.BOOMTICK_SESSION_EXEC = "0";
  });

  afterEach(async () => {
    delete process.env.BOOMTICK_SESSION_EXEC;
    delete process.env.BOOMTICK_EXECUTOR_CLI;
    try {
      await fs.rm(tmpRepoDir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  });

  it("agent_dispatch spawns a task-scoped session bound to the specified worktree", async () => {
    const dispatchRes = await agentDispatchHandler({
      worktreeId: tmpWorktreeDir,
      brief: "Fix bug in test.txt",
      model: "qwen2.5-coder:7b",
    });

    expect(dispatchRes.sessionId).toBeDefined();
    expect(dispatchRes.worktreeId).toBe(tmpWorktreeDir);
    expect(dispatchRes.status).toBe("running");
    expect(typeof dispatchRes.startedAt).toBe("number");

    // Status check
    const statusRes = await agentStatusHandler({ sessionId: dispatchRes.sessionId });
    expect(statusRes.sessionId).toBe(dispatchRes.sessionId);
    expect(statusRes.state).toBe("running");
    expect(statusRes.lastCheckpoint).toBe("worktree_setup");
  });

  it("attempting to access or edit files outside the worktree root throws a containment error", async () => {
    const manager = SessionManager.getInstance();

    // Inside target works
    const valid = manager.assertContainedPath(tmpWorktreeDir, "test.txt");
    expect(valid).toContain(tmpWorktreeDir);

    // Traversal outside throws
    expect(() => {
      manager.assertContainedPath(tmpWorktreeDir, "../outside.txt");
    }).toThrow(/Containment error/);

    expect(() => {
      manager.assertContainedPath(tmpWorktreeDir, "/etc/passwd");
    }).toThrow(/Containment error/);
  });

  it("agent_status reports accurate status and changed files", async () => {
    const dispatchRes = await agentDispatchHandler({
      worktreeId: tmpWorktreeDir,
      brief: "Update test.txt",
    });

    // Make an edit inside worktree
    await fs.writeFile(path.join(tmpWorktreeDir, "test.txt"), "modified line\n");

    const statusRes = await agentStatusHandler({ sessionId: dispatchRes.sessionId });
    expect(statusRes.changedFiles).toContain("test.txt");
  });

  it("agent_logs streams and retrieves session output tails", async () => {
    const dispatchRes = await agentDispatchHandler({
      worktreeId: tmpWorktreeDir,
      brief: "Log testing",
    });

    const manager = SessionManager.getInstance();
    await manager.appendLogs(dispatchRes.sessionId, ["Line 1", "Line 2", "Line 3"]);

    const logsRes = await agentLogsHandler({
      sessionId: dispatchRes.sessionId,
      tail: 2,
    });

    expect(logsRes.logs.length).toBe(2);
    expect(logsRes.logs).toEqual(["Line 2", "Line 3"]);
    expect(logsRes.totalLines).toBeGreaterThanOrEqual(4);
  });

  it("commit_patch fails if attempting to commit files not modified in the session", async () => {
    const dispatchRes = await agentDispatchHandler({
      worktreeId: tmpWorktreeDir,
      brief: "Commit testing",
    });

    const manager = SessionManager.getInstance();

    // Modify test.txt
    await fs.writeFile(path.join(tmpWorktreeDir, "test.txt"), "new content\n");

    // Attempt to commit a file that was not modified (e.g. unmod.txt)
    await expect(
      manager.commitPatch(dispatchRes.sessionId, "patch commit", ["unmod.txt"])
    ).rejects.toThrow(/cannot commit files not modified/);

    // Successfully commit the modified file
    const commitRes = await manager.commitPatch(dispatchRes.sessionId, "patch commit", ["test.txt"]);
    expect(commitRes.success).toBe(true);
    expect(commitRes.commitSha).toBeDefined();

    const finalStatus = await agentStatusHandler({ sessionId: dispatchRes.sessionId });
    expect(finalStatus.state).toBe("done");
  });
});

describe("agent_dispatch real execution", () => {
  let tmpRepoDir: string;
  let tmpWorktreeDir: string;

  async function waitForState(sessionId: string, states: string[], timeoutMs = 10000) {
    const manager = SessionManager.getInstance();
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const s = await manager.loadSession(sessionId);
      if (s && states.includes(s.state)) {
        return s;
      }
      if (Date.now() > deadline) {
        throw new Error(`timed out waiting for ${states.join("/")}`);
      }
      await new Promise((r) => setTimeout(r, 50));
    }
  }

  beforeEach(async () => {
    tmpRepoDir = await fs.mkdtemp(path.join(os.tmpdir(), "bt-exec-"));
    tmpWorktreeDir = path.join(tmpRepoDir, ".worktrees", "exec-wt");
    await fs.mkdir(tmpWorktreeDir, { recursive: true });
    const { execSync } = await import("child_process");
    execSync("git init -b main", { cwd: tmpWorktreeDir });
    execSync('git config user.email "test@example.com"', { cwd: tmpWorktreeDir });
    execSync('git config user.name "Test Runner"', { cwd: tmpWorktreeDir });
    SessionManager.getInstance().reset();
    delete process.env.BOOMTICK_SESSION_EXEC;
  });

  afterEach(async () => {
    delete process.env.BOOMTICK_SESSION_EXEC;
    delete process.env.BOOMTICK_EXECUTOR_CLI;
    try {
      await fs.rm(tmpRepoDir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  });

  it("exit 0 flips the session to done", async () => {
    process.env.BOOMTICK_EXECUTOR_CLI = "true";
    const dispatchRes = await agentDispatchHandler({
      worktreeId: tmpWorktreeDir,
      brief: "no-op",
    });
    const s = await waitForState(dispatchRes.sessionId, ["done", "failed"]);
    expect(s.state).toBe("done");
    expect(s.lastCheckpoint).toBe("execution_done");
  });

  it("nonzero exit flips the session to failed", async () => {
    process.env.BOOMTICK_EXECUTOR_CLI = "false";
    const dispatchRes = await agentDispatchHandler({
      worktreeId: tmpWorktreeDir,
      brief: "no-op",
    });
    const s = await waitForState(dispatchRes.sessionId, ["done", "failed"]);
    expect(s.state).toBe("failed");
    expect(s.lastCheckpoint).toBe("execution_failed");
  });

  it("streams child output into session logs", async () => {
    process.env.BOOMTICK_EXECUTOR_CLI = "echo";
    const dispatchRes = await agentDispatchHandler({
      worktreeId: tmpWorktreeDir,
      brief: "stream-marker-xyz",
    });
    const s = await waitForState(dispatchRes.sessionId, ["done", "failed"]);
    expect(s.state).toBe("done");
    expect(s.logs.join("\n")).toContain("stream-marker-xyz");
    expect(s.logs.join("\n")).toContain("-p --system-prompt");
  });

  it("exec disabled leaves bookkeeping-only behavior", async () => {
    process.env.BOOMTICK_SESSION_EXEC = "0";
    process.env.BOOMTICK_EXECUTOR_CLI = "false";
    const dispatchRes = await agentDispatchHandler({
      worktreeId: tmpWorktreeDir,
      brief: "no-op",
    });
    await new Promise((r) => setTimeout(r, 300));
    const statusRes = await agentStatusHandler({ sessionId: dispatchRes.sessionId });
    expect(statusRes.state).toBe("running");
    expect(statusRes.lastCheckpoint).toBe("worktree_setup");
  });
});
