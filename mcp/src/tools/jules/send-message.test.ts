import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { sendJulesMessageHandler } from "./send-message.js";
import { setupTestEnv, teardownTestEnv } from "../../lib/test-utils.js";

describe("sendJulesMessageHandler", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    setupTestEnv();
    global.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            name: "sessions/123",
          }),
      })
    ) as any;
  });

  afterEach(() => {
    teardownTestEnv();
    global.fetch = originalFetch;
  });

  it("should send a message", async () => {
    const result = await sendJulesMessageHandler({ id: "123", message: "hi" });
    expect(result.id).toBe("123");
    expect(result.status).toBe("success");
  });
});
