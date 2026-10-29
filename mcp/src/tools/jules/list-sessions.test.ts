import { describe, it, expect, vi, beforeEach } from "vitest";
import { listJulesSessionsHandler } from "./list-sessions.js";
import { runTDCli } from "./cli.js";
import { createSuccessResult } from "../../lib/result.js";

vi.mock("./cli.js", () => ({
  runTDCli: vi.fn(),
}));

describe("listJulesSessionsHandler", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should return an object with sessions array and work with createSuccessResult", async () => {
    vi.mocked(runTDCli).mockResolvedValueOnce({
      sessions: [
        {
          name: "sessions/session-1",
          state: "COMPLETED",
          createTime: "2025-01-01T00:00:00Z",
          outputs: [
            {
              pullRequest: {
                url: "https://github.com/owner/repo/pull/1",
              },
            },
          ],
        },
      ],
    });

    const result = await listJulesSessionsHandler({});

    expect(result).toEqual({
      sessions: [
        {
          id: "session-1",
          status: "COMPLETED",
          createdAt: new Date("2025-01-01T00:00:00Z"),
          pullRequestUrl: "https://github.com/owner/repo/pull/1",
        },
      ],
    });

    const mcpSuccessResult = createSuccessResult(result);
    expect(mcpSuccessResult.structuredContent).toEqual({
      sessions: [
        {
          id: "session-1",
          status: "COMPLETED",
          createdAt: new Date("2025-01-01T00:00:00Z"),
          pullRequestUrl: "https://github.com/owner/repo/pull/1",
        },
      ],
    });
    expect(mcpSuccessResult.structuredContent).not.toBeInstanceOf(Array);
  });

  it("should handle empty sessions array", async () => {
    vi.mocked(runTDCli).mockResolvedValueOnce({});

    const result = await listJulesSessionsHandler({});

    expect(result).toEqual({ sessions: [] });
    const mcpSuccessResult = createSuccessResult(result);
    expect(mcpSuccessResult.structuredContent).toEqual({ sessions: [] });
  });
});
