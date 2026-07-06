import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { getJulesMessagesHandler } from "./get-messages.js";
import * as shell from "../../lib/shell.js";
import { setupTestEnv, teardownTestEnv } from "../../lib/test-utils.js";

vi.mock("../../lib/shell.js", () => ({
  runCommand: vi.fn(),
}));

describe("getJulesMessagesHandler", () => {
  beforeEach(() => {
    setupTestEnv();
  });

  afterEach(() => {
    teardownTestEnv();
    vi.clearAllMocks();
  });

  it("should return messages from td-cli", async () => {
    const mockMessages = [
      {
        role: "user",
        content: "Hello Jules",
        time: new Date().toISOString(),
      },
      {
        role: "jules",
        content: "Applying fixes...",
        time: new Date().toISOString(),
      },
    ];

    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify({ status: "success", messages: mockMessages }),
      stderr: "",
      exitCode: 0,
      durationMs: 0,
      command: "td-cli agent messages"
    });

    const result = await getJulesMessagesHandler({ sessionId: "123" });
    expect(result.id).toBe("123");
    expect(result.messages.length).toBe(2);
    expect(result.messages[0].role).toBe("user");
    expect(result.messages[0].content).toBe("Hello Jules");

    expect(shell.runCommand).toHaveBeenCalledWith("td-cli", [
      "agent", "messages", "123"
    ]);
  });
});
