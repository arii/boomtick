import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { checkJulesStatusHandler } from "./repo.check_jules_status.js";

describe("repo.check_jules_status MCP Tool Handler", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    vi.clearAllMocks();
    process.env = { ...originalEnv };
    delete process.env.TASK_ID;
    delete process.env.JULES_API_KEY;
    global.fetch = vi.fn();
  });

  afterEach(() => {
    process.env = originalEnv;
    vi.restoreAllMocks();
  });

  it("returns NOT_FOUND status if no session ID or JULES_API_KEY is available", async () => {
    const result = await checkJulesStatusHandler({});
    expect(result.status).toBe("NOT_FOUND");
    expect(result.completed).toBe(false);
  });

  it("checks Jules session status and returns response object", async () => {
    process.env.JULES_API_KEY = "test-api-key";

    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        name: "sessions/test-session-123",
        state: "SUCCEEDED",
        outputs: [
          {
            pullRequest: {
              url: "https://github.com/org/repo/pull/100",
              branch: "remediation-branch-123",
            },
          },
        ],
      }),
    } as any);

    const result = await checkJulesStatusHandler({
      sessionId: "test-session-123",
    });

    expect(result.sessionId).toBe("sessions/test-session-123");
    expect(result.status).toBe("COMPLETED");
    expect(result.completed).toBe(true);
    expect(result.remediationBranch).toBe("remediation-branch-123");
    expect(result.pullRequestUrl).toBe("https://github.com/org/repo/pull/100");
  });
});
