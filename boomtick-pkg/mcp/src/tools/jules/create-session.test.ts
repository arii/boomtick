import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createJulesSessionHandler } from "./create-session.js";
import * as shell from "../../lib/shell.js";
import { setupTestEnv, teardownTestEnv } from "../../lib/test-utils.js";

vi.mock("../../lib/shell.js", () => ({
  runCommand: vi.fn(),
}));

describe("createJulesSessionHandler", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    setupTestEnv();
    global.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            name: "sessions/1234567890",
            state: "PENDING",
            createTime: new Date().toISOString(),
          }),
      })
    ) as any;
  });

  afterEach(() => {
    teardownTestEnv();
    global.fetch = originalFetch;
    vi.clearAllMocks();
  });

  it("should create a session with just task", async () => {
    const result = await createJulesSessionHandler({ task: "do work" });
    expect(result.id).toBe("1234567890");
    expect(result.status).toBe("IN_PROGRESS");
    expect(result.createdAt).toBeInstanceOf(Date);

    expect(global.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        body: expect.stringContaining('"startingBranch":"main"')
      })
    );
  });

  it("should create a session with specific branch", async () => {
    const result = await createJulesSessionHandler({ task: "do work", branch: "feature-x" });
    expect(result.id).toBe("1234567890");

    expect(global.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        body: expect.stringContaining('"startingBranch":"feature-x"')
      })
    );
  });

  it("should create a session with PR number", async () => {
    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify({ headRefName: "pr-branch" }),
      stderr: "",
      exitCode: 0,
      durationMs: 10,
      command: "gh pr view"
    });

    const result = await createJulesSessionHandler({ task: "do work", pr: 42 });
    expect(result.id).toBe("1234567890");

    expect(shell.runCommand).toHaveBeenCalledWith("gh", [
      "pr",
      "view",
      "42",
      "--json",
      "headRefName"
    ]);

    expect(global.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        body: expect.stringContaining('"startingBranch":"pr-branch"')
      })
    );
  });

  it("should throw error if PR view fails", async () => {
    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: "",
      stderr: "PR not found",
      exitCode: 1,
      durationMs: 10,
      command: "gh pr view"
    });

    await expect(createJulesSessionHandler({ task: "do work", pr: 999 }))
      .rejects.toThrow("Failed to get PR info for PR #999: PR not found");
  });

  it("should throw descriptive error if PR JSON is invalid", async () => {
    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: "invalid json",
      stderr: "",
      exitCode: 0,
      durationMs: 10,
      command: "gh pr view"
    });

    await expect(createJulesSessionHandler({ task: "do work", pr: 42 }))
      .rejects.toThrow(/Failed to parse PR info for PR #42/);
  });
});
