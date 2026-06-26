import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { triggerJulesFeedbackHandler } from "./trigger-feedback.js";
import * as shell from "../../lib/shell.js";
import { setupTestEnv, teardownTestEnv } from "../../lib/test-utils.js";

vi.mock("../../lib/shell.js", () => ({
  runCommand: vi.fn(),
}));

describe("triggerJulesFeedbackHandler", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    setupTestEnv();
    global.fetch = vi.fn().mockImplementation((url) => {
      if (url.includes("/sessions/123")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            name: "sessions/123",
            outputs: [{ pullRequest: { url: "https://github.com/arii/tech-dancer/pull/42" } }]
          }),
        });
      }
      if (url.includes(":sendMessage")) {
        return Promise.resolve({ ok: true });
      }
      return Promise.reject(new Error("Unknown fetch"));
    }) as any;
  });

  afterEach(() => {
    teardownTestEnv();
    global.fetch = originalFetch;
    vi.clearAllMocks();
  });

  it("should send success feedback when CI passes", async () => {
    vi.mocked(shell.runCommand).mockImplementation(async (cmd, args) => {
      if (args[0] === "pr" && args[1] === "view") {
        return { stdout: JSON.stringify({ headRefOid: "sha123" }), stderr: "", exitCode: 0, durationMs: 0, command: "" };
      }
      if (args[0] === "api" && args[1].includes("/check-runs")) {
        return {
          stdout: JSON.stringify({
            check_runs: [{ name: "Test", status: "completed", conclusion: "success" }]
          }),
          stderr: "",
          exitCode: 0,
          durationMs: 0,
          command: ""
        };
      }
      return { stdout: "", stderr: "", exitCode: 0, durationMs: 0, command: "" };
    });

    const result = await triggerJulesFeedbackHandler({ sessionId: "123" });
    expect(result.status).toBe("success");
    expect(result.feedback).toBe("All checks passed successfully. You may proceed.");

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining(":sendMessage"),
      expect.objectContaining({
        body: expect.stringContaining("All checks passed successfully.")
      })
    );
  });

  it("should send failure feedback with extracted logs when CI fails", async () => {
    vi.mocked(shell.runCommand).mockImplementation(async (cmd, args) => {
      if (args[0] === "pr" && args[1] === "view") {
        return { stdout: JSON.stringify({ headRefOid: "sha123" }), stderr: "", exitCode: 0, durationMs: 0, command: "" };
      }
      if (args[0] === "api" && args[1].includes("/check-runs")) {
        return {
          stdout: JSON.stringify({
            check_runs: [{ name: "Lint", status: "completed", conclusion: "failure", external_id: "job789" }]
          }),
          stderr: "",
          exitCode: 0,
          durationMs: 0,
          command: ""
        };
      }
      if (args[0] === "api" && args[1].includes("/jobs/job789/logs")) {
        return {
          stdout: "src/App.tsx:10:5 - error TS123: Missing semicolon",
          stderr: "",
          exitCode: 0,
          durationMs: 0,
          command: ""
        };
      }
      return { stdout: "", stderr: "", exitCode: 0, durationMs: 0, command: "" };
    });

    const result = await triggerJulesFeedbackHandler({ sessionId: "123" });
    expect(result.status).toBe("success");
    expect(result.feedback).toContain("The CI pipeline reported failures");
    expect(result.feedback).toContain("File: `src/App.tsx:10` (typescript)");
    expect(result.feedback).toContain("Message: TS123: Missing semicolon");

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining(":sendMessage"),
      expect.objectContaining({
        body: expect.stringContaining("The CI pipeline reported failures")
      })
    );
  });
});
