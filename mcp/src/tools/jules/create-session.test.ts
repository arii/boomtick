import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createJulesSessionHandler } from "./create-session.js";
import * as shell from "../../lib/shell.js";
import { setupTestEnv, teardownTestEnv } from "../../lib/test-utils.js";

vi.mock("../../lib/shell.js", () => ({
  runCommand: vi.fn(),
}));

describe("createJulesSessionHandler", () => {
  beforeEach(() => {
    setupTestEnv();
    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify({
        session: {
          name: "sessions/1234567890",
          state: "IN_PROGRESS",
          createTime: new Date().toISOString(),
        }
      }),
      stderr: "",
      exitCode: 0,
      durationMs: 10,
      command: "td-cli agent dispatch"
    });
  });

  afterEach(() => {
    teardownTestEnv();
    vi.clearAllMocks();
  });

  it("should create a session with just task", async () => {
    const result = await createJulesSessionHandler({ task: "do work" });
    expect(result.id).toBe("1234567890");
    expect(result.status).toBe("IN_PROGRESS");
    expect(result.createdAt).toBeInstanceOf(Date);

    expect(shell.runCommand).toHaveBeenCalledWith("td-cli", [
      "agent", "dispatch", "main", "do work"
    ]);
  });

  it("should create a session with specific branch", async () => {
    const result = await createJulesSessionHandler({ task: "do work", branch: "feature-x" });
    expect(result.id).toBe("1234567890");

    expect(shell.runCommand).toHaveBeenCalledWith("td-cli", [
      "agent", "dispatch", "feature-x", "do work"
    ]);
  });

  it("should create a session with PR number", async () => {
    vi.mocked(shell.runCommand).mockImplementation(async (cmd, args) => {
      if (args[1] === "view") {
        return {
          stdout: JSON.stringify({ pr: { headRefName: "pr-branch" } }),
          stderr: "",
          exitCode: 0,
          durationMs: 10,
          command: "td-cli gh view"
        };
      }
      return {
        stdout: JSON.stringify({
          session: {
            name: "sessions/1234567890",
            state: "IN_PROGRESS",
            createTime: new Date().toISOString(),
          }
        }),
        stderr: "",
        exitCode: 0,
        durationMs: 10,
        command: "td-cli agent dispatch"
      };
    });

    const result = await createJulesSessionHandler({ task: "do work", pr: 42 });
    expect(result.id).toBe("1234567890");

    expect(shell.runCommand).toHaveBeenCalledWith("td-cli", [
      "gh", "view", "42"
    ]);

    expect(shell.runCommand).toHaveBeenCalledWith("td-cli", [
      "agent", "dispatch", "pr-branch", "do work"
    ]);
  });

  it("should throw error if PR view fails", async () => {
    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: "",
      stderr: "PR not found",
      exitCode: 1,
      durationMs: 10,
      command: "td-cli gh view"
    });

    await expect(createJulesSessionHandler({ task: "do work", pr: 999 }))
      .rejects.toThrow("Failed to create session: PR not found");
  });

  it("should throw descriptive error if PR JSON is invalid", async () => {
    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: "invalid json",
      stderr: "",
      exitCode: 0,
      durationMs: 10,
      command: "td-cli gh view"
    });

    await expect(createJulesSessionHandler({ task: "do work", pr: 42 }))
      .rejects.toThrow(/Unexpected token/);
  });
});
