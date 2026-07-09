import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { sendJulesMessageHandler } from "./send-message.js";
import * as shell from "../../lib/shell.js";
import { setupTestEnv, teardownTestEnv } from "../../lib/test-utils.js";

vi.mock("../../lib/shell.js", () => ({
  runCommand: vi.fn(),
}));

describe("sendJulesMessageHandler", () => {
  beforeEach(() => {
    setupTestEnv();
  });

  afterEach(() => {
    teardownTestEnv();
    vi.clearAllMocks();
  });

  it("should send a message via td-cli", async () => {
    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify({ status: "success", message: "Message sent successfully" }),
      stderr: "",
      exitCode: 0,
      durationMs: 0,
      command: "td-cli agent send"
    });

    const result = await sendJulesMessageHandler({ sessionId: "123", message: "hi" });
    expect(result.id).toBe("123");
    expect(result.status).toBe("success");

    expect(shell.runCommand).toHaveBeenCalledWith("td-cli", [
      "agent", "send", "123", "hi"
    ]);
  });

  it("should support batch message sending", async () => {
    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify({
        status: "success",
        message: "Batch send completed. 2/2 successful.",
        results: [
          { sessionId: "s1", status: "success" },
          { sessionId: "s2", status: "success" }
        ]
      }),
      stderr: "",
      exitCode: 0,
      durationMs: 0,
      command: "td-cli agent send"
    });

    const result = await sendJulesMessageHandler({
      sessionId: ["sessions/s1", "sessions/s2"],
      message: "hi batch"
    });

    expect(result.id).toEqual(["s1", "s2"]);
    expect(result.status).toBe("success");

    expect(shell.runCommand).toHaveBeenCalledWith("td-cli", [
      "agent", "send", "sessions/s1,sessions/s2", "hi batch"
    ]);
  });
});
