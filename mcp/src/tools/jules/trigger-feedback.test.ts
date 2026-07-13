import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { triggerJulesFeedbackHandler } from "./trigger-feedback.js";
import * as shell from "../../lib/shell.js";
import { setupTestEnv, teardownTestEnv } from "../../lib/test-utils.js";

vi.mock("../../lib/shell.js", () => ({
  runCommand: vi.fn(),
}));

describe("triggerJulesFeedbackHandler", () => {
  beforeEach(() => {
    setupTestEnv();
  });

  afterEach(() => {
    teardownTestEnv();
    vi.clearAllMocks();
  });

  it("should return success output from td-cli", async () => {
    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify({ status: "success", feedback: "All checks passed successfully. You may proceed." }),
      stderr: "",
      exitCode: 0,
      durationMs: 0,
      command: "td-cli agent trigger-feedback"
    });

    const result = await triggerJulesFeedbackHandler({ sessionId: "123" });
    expect(result.status).toBe("success");
    expect(result.feedback).toBe("All checks passed successfully. You may proceed.");

    expect(shell.runCommand).toHaveBeenCalledWith("td-cli", [
      "agent", "trigger-feedback", "123"
    ]);
  });

  it("should throw error if td-cli returns error", async () => {
    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify({ status: "error", message: "Session not found" }),
      stderr: "",
      exitCode: 0,
      durationMs: 0,
      command: "td-cli agent trigger-feedback"
    });

    await expect(triggerJulesFeedbackHandler({ sessionId: "123" }))
      .rejects.toThrow("Failed to trigger feedback: Session not found");
  });
});
