import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { agentDiscussHandler } from "./agent.discuss.js";
import { SessionManager, AgentSession } from "../lib/session_manager.js";
import * as shell from "../lib/shell.js";
import * as git from "../lib/git.js";
import * as commitPatch from "./repo.commit_patch.js";
import * as createPullRequest from "./github.create_pull_request.js";

describe("agent_discuss MCP tool", () => {
  let sessionManager: SessionManager;
  const mockSessionId = "sess-12345";
  const mockWorktreePath = "/tmp/mock-worktree";

  beforeEach(() => {
    SessionManager.resetInstance();
    sessionManager = SessionManager.getInstance();

    const session: AgentSession = {
      sessionId: mockSessionId,
      worktreeId: "wt-repair-1",
      worktreePath: mockWorktreePath,
      branch: "agent/fix-1-timestamp",
      baseBranch: "main",
      brief: "Fix bug in calculation module",
      state: "running",
      retries: 0,
      maxRetries: 3,
      transcript: ["Initial dispatch"],
      logs: [],
      lastVerification: {
        testsPassed: true,
        exitCode: 0,
      },
      createdAt: Date.now() - 10000,
      updatedAt: Date.now() - 10000,
    };
    sessionManager.registerSession(session);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("Topic: status", () => {
    it("returns state, diff stats, and verification status without mutations", async () => {
      vi.spyOn(shell, "runCommand").mockImplementation(async (cmd, args) => {
        if (cmd === "git" && args[0] === "status") {
          return { exitCode: 0, stdout: " M src/calc.ts\n?? src/new.ts\n", stderr: "" };
        }
        if (cmd === "git" && args[0] === "diff" && args[1] === "--stat") {
          return { exitCode: 0, stdout: " src/calc.ts | 4 ++--\n 1 file changed, 2 insertions(+), 2 deletions(-)\n", stderr: "" };
        }
        return { exitCode: 0, stdout: "", stderr: "" };
      });

      const res = await agentDiscussHandler({
        sessionId: mockSessionId,
        topic: "status",
      });

      expect(res.status).toBe("success");
      expect(res.topic).toBe("status");
      expect(res.data).toBeDefined();
      expect(res.data?.state).toBe("running");
      expect(res.data?.branch).toBe("agent/fix-1-timestamp");
      expect(res.data?.diffStat?.summary).toBe("+2 / -2");
      expect(res.data?.diffStat?.insertions).toBe(2);
      expect(res.data?.diffStat?.deletions).toBe(2);
      expect(res.data?.lastVerification?.testsPassed).toBe(true);
    });
  });

  describe("Topic: review-diff", () => {
    it("returns unified diff and verification results cleanly formatted", async () => {
      const mockDiff = "diff --git a/src/calc.ts b/src/calc.ts\n--- a/src/calc.ts\n+++ b/src/calc.ts\n@@ -1,2 +1,2 @@\n-const x = 1;\n+const x = 2;\n";
      vi.spyOn(shell, "runCommand").mockImplementation(async (cmd, args) => {
        if (cmd === "git" && args[0] === "diff" && args[1] === "main...HEAD") {
          return { exitCode: 0, stdout: mockDiff, stderr: "" };
        }
        return { exitCode: 0, stdout: "", stderr: "" };
      });

      const res = await agentDiscussHandler({
        sessionId: mockSessionId,
        topic: "review-diff",
      });

      expect(res.status).toBe("success");
      expect(res.topic).toBe("review-diff");
      expect(res.data?.unifiedDiff).toBe(mockDiff);
      expect(res.data?.verificationOutputs?.testsPassed).toBe(true);
    });
  });

  describe("Topic: request-changes", () => {
    it("requires non-empty message", async () => {
      await expect(
        agentDiscussHandler({
          sessionId: mockSessionId,
          topic: "request-changes",
          message: "",
        })
      ).rejects.toThrow(/Message is required/);

      await expect(
        agentDiscussHandler({
          sessionId: mockSessionId,
          topic: "request-changes",
        })
      ).rejects.toThrow(/Message is required/);
    });

    it("appends message to brief and increments retry attempt", async () => {
      const res = await agentDiscussHandler({
        sessionId: mockSessionId,
        topic: "request-changes",
        message: "Please add unit tests for edge cases.",
      });

      expect(res.status).toBe("success");
      expect(res.data?.retries).toBe(1);
      expect(res.data?.state).toBe("running");
      expect(res.data?.brief).toContain("Please add unit tests for edge cases.");

      const updatedSession = sessionManager.getSession(mockSessionId);
      expect(updatedSession.retries).toBe(1);
      expect(updatedSession.brief).toContain("[Change Request 1]");
    });

    it("marks session failed when retry budget of 3 is exceeded", async () => {
      // Retries 1, 2, 3
      await agentDiscussHandler({ sessionId: mockSessionId, topic: "request-changes", message: "Feedback 1" });
      await agentDiscussHandler({ sessionId: mockSessionId, topic: "request-changes", message: "Feedback 2" });
      await agentDiscussHandler({ sessionId: mockSessionId, topic: "request-changes", message: "Feedback 3" });

      expect(sessionManager.getSession(mockSessionId).retries).toBe(3);

      // 4th retry exceeds budget
      await expect(
        agentDiscussHandler({
          sessionId: mockSessionId,
          topic: "request-changes",
          message: "Feedback 4",
        })
      ).rejects.toThrow(/Retry budget of 3 exceeded/);

      expect(sessionManager.getSession(mockSessionId).state).toBe("failed");
    });
  });

  describe("Topic: approve-merge", () => {
    it("requires writeMode: true", async () => {
      await expect(
        agentDiscussHandler({
          sessionId: mockSessionId,
          topic: "approve-merge",
          writeMode: false,
          pushMode: true,
        })
      ).rejects.toThrow(/writeMode: true is required/);
    });

    it("requires pushMode: true", async () => {
      await expect(
        agentDiscussHandler({
          sessionId: mockSessionId,
          topic: "approve-merge",
          writeMode: true,
          pushMode: false,
        })
      ).rejects.toThrow(/pushMode: true is required/);
    });

    it("stages, commits, pushes, creates PR, and cleans up worktree when authorized", async () => {
      vi.spyOn(shell, "runCommand").mockImplementation(async (cmd, args) => {
        if (cmd === "git" && args[0] === "status") {
          return { exitCode: 0, stdout: " M src/calc.ts\n", stderr: "" };
        }
        if (cmd === "git" && args[0] === "push") {
          return { exitCode: 0, stdout: "Everything up-to-date", stderr: "" };
        }
        return { exitCode: 0, stdout: "", stderr: "" };
      });

      const commitSpy = vi.spyOn(commitPatch, "commitPatchHandler").mockResolvedValue({
        success: true,
        commitSha: "abc1234def",
        changedFiles: ["src/calc.ts"],
      });

      const prSpy = vi.spyOn(createPullRequest, "createPullRequestHandler").mockResolvedValue({
        success: true,
        url: "https://github.com/arii/boomtick/pull/999",
      });

      const removeWorktreeSpy = vi.spyOn(git, "removeWorktree").mockResolvedValue();

      const res = await agentDiscussHandler({
        sessionId: mockSessionId,
        topic: "approve-merge",
        writeMode: true,
        pushMode: true,
      });

      expect(res.status).toBe("success");
      expect(res.data?.pullRequestUrl).toBe("https://github.com/arii/boomtick/pull/999");
      expect(commitSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          worktreePath: mockWorktreePath,
          writeMode: true,
          allowedFiles: ["src/calc.ts"],
        })
      );
      expect(prSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          head: "agent/fix-1-timestamp",
          base: "main",
          draft: false,
        })
      );
      expect(removeWorktreeSpy).toHaveBeenCalledWith(mockWorktreePath, undefined);

      const session = sessionManager.getSession(mockSessionId);
      expect(session.state).toBe("done");
      expect(session.pullRequestUrl).toBe("https://github.com/arii/boomtick/pull/999");
    });
  });

  describe("Topic: abandon", () => {
    it("requires writeMode: true", async () => {
      await expect(
        agentDiscussHandler({
          sessionId: mockSessionId,
          topic: "abandon",
          writeMode: false,
        })
      ).rejects.toThrow(/writeMode: true is required/);
    });

    it("cancels session and forces worktree removal", async () => {
      const removeWorktreeSpy = vi.spyOn(git, "removeWorktree").mockResolvedValue();

      const res = await agentDiscussHandler({
        sessionId: mockSessionId,
        topic: "abandon",
        writeMode: true,
      });

      expect(res.status).toBe("success");
      expect(res.data?.state).toBe("abandoned");
      expect(removeWorktreeSpy).toHaveBeenCalledWith(mockWorktreePath, undefined);

      const session = sessionManager.getSession(mockSessionId);
      expect(session.state).toBe("abandoned");
    });
  });

  describe("Session locking and safety", () => {
    it("prevents concurrent conflicting discuss calls on the same session", async () => {
      let call1Finished = false;
      let call2StartedWhile1Running = false;

      // Slow down first call artificially
      vi.spyOn(shell, "runCommand").mockImplementation(async (cmd, args) => {
        if (cmd === "git" && args[0] === "status") {
          await new Promise((r) => setTimeout(r, 50));
          return { exitCode: 0, stdout: "", stderr: "" };
        }
        return { exitCode: 0, stdout: "", stderr: "" };
      });

      const p1 = agentDiscussHandler({
        sessionId: mockSessionId,
        topic: "status",
      }).then((res) => {
        call1Finished = true;
        return res;
      });

      const p2 = agentDiscussHandler({
        sessionId: mockSessionId,
        topic: "status",
      }).then((res) => {
        if (!call1Finished) {
          call2StartedWhile1Running = true;
        }
        return res;
      });

      const [r1, r2] = await Promise.all([p1, p2]);
      expect(r1.status).toBe("success");
      expect(r2.status).toBe("success");
      expect(call2StartedWhile1Running).toBe(false);
    });
  });
});
