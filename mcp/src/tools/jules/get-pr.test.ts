import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { getJulesPullRequestHandler } from "./get-pr.js";
import * as shell from "../../lib/shell.js";
import { setupTestEnv, teardownTestEnv } from "../../lib/test-utils.js";

vi.mock("../../lib/shell.js", () => ({
  runCommand: vi.fn(),
}));

describe("getJulesPullRequestHandler", () => {
  beforeEach(() => {
    setupTestEnv();
  });

  afterEach(() => {
    teardownTestEnv();
    vi.clearAllMocks();
  });

  it("should get PR from td-cli", async () => {
    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify({
        status: "success",
        session: {
          name: "sessions/123",
          outputs: [{ pullRequest: { url: "https://github.com/pr/1" } }]
        }
      }),
      stderr: "",
      exitCode: 0,
      durationMs: 0,
      command: "td-cli agent get-session"
    });

    const result = await getJulesPullRequestHandler({ id: "123" });
    expect(result.id).toBe("123");
    expect(result.pullRequestUrl).toBe("https://github.com/pr/1");

    expect(shell.runCommand).toHaveBeenCalledWith("td-cli", [
      "agent", "get-session", "123"
    ]);
  });
});
