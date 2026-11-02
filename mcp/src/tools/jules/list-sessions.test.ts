import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { listJulesSessionsHandler } from "./list-sessions.js";
import * as shell from "../../lib/shell.js";
import { setupTestEnv, teardownTestEnv } from "../../lib/test-utils.js";

vi.mock("../../lib/shell.js", () => ({
  runCommand: vi.fn(),
}));

describe("listJulesSessionsHandler", () => {
  beforeEach(() => {
    setupTestEnv();
  });

  afterEach(() => {
    teardownTestEnv();
    vi.clearAllMocks();
  });

  it("should return sessions wrapped in an object with sessions key", async () => {
    const mockRawSessions = [
      {
        name: "sessions/s1",
        state: "COMPLETED",
        createTime: "2025-01-01T00:00:00Z",
      },
      {
        name: "sessions/s2",
        state: "IN_PROGRESS",
        createTime: "2025-01-02T00:00:00Z",
      },
    ];

    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify({ status: "success", sessions: mockRawSessions }),
      stderr: "",
      exitCode: 0,
      durationMs: 0,
      command: "td agent sync",
    });

    const result = await listJulesSessionsHandler({});
    expect(result).toHaveProperty("sessions");
    expect(Array.isArray(result.sessions)).toBe(true);
    expect(result.sessions).toHaveLength(2);
    expect(result.sessions![0].id).toBe("s1");
    expect(result.sessions![0].status).toBe("COMPLETED");

    expect(shell.runCommand).toHaveBeenCalledWith("td", ["agent", "sync"]);
  });

  it("should handle empty sessions list gracefully", async () => {
    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify({ status: "success", sessions: [] }),
      stderr: "",
      exitCode: 0,
      durationMs: 0,
      command: "td agent sync",
    });

    const result = await listJulesSessionsHandler({});
    expect(result).toEqual({ sessions: [] });
  });

  it("should throw explicit error naming JULES_API_KEY and resolution path when JULES_API_KEY is unset", async () => {
    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify({
        status: "success",
        sessions: [],
        warning: "JULES_API_KEY unset",
      }),
      stderr: "",
      exitCode: 0,
      durationMs: 0,
      command: "td agent sync",
    });

    await expect(listJulesSessionsHandler({})).rejects.toThrow(
      /JULES_API_KEY is not set or empty \(checked in environment and .*\)/
    );
  });
});
