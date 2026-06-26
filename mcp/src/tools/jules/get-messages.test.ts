import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { getJulesMessagesHandler } from "./get-messages.js";
import { setupTestEnv, teardownTestEnv } from "../../lib/test-utils.js";

describe("getJulesMessagesHandler", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    setupTestEnv();
    global.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            activities: [
              {
                name: "sessions/123/activities/abc",
                createTime: new Date().toISOString(),
                originator: "user",
                userMessaged: { userMessage: { body: "Hello Jules" } },
                id: "abc",
              },
              {
                name: "sessions/123/activities/def",
                createTime: new Date().toISOString(),
                originator: "agent",
                progressUpdated: { description: "Applying fixes..." },
                id: "def",
              },
            ],
          }),
      })
    ) as any;
  });

  afterEach(() => {
    teardownTestEnv();
    global.fetch = originalFetch;
  });

  it("should return messages", async () => {
    const result = await getJulesMessagesHandler({ id: "123" });
    expect(result.id).toBe("123");
    expect(result.messages.length).toBe(2);
    expect(result.messages[0].role).toBe("user");
    expect(result.messages[0].content).toBe("Hello Jules");
  });
});
