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

    const result = await sendJulesMessageHandler({ id: "123", message: "hi" });
    expect(result.id).toBe("123");
    expect(result.status).toBe("success");

    expect(shell.runCommand).toHaveBeenCalledWith("td-cli", [
      "agent", "send", "123", "hi"
    ]);
  });
});
