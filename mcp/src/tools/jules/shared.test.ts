import { describe, it, expect } from "vitest";
import { parseJulesSession } from "./shared.js";

describe("jules/shared", () => {
  describe("parseJulesSession", () => {
    it("should strip 'sessions/' prefix from session name to form ID", () => {
      const input = {
        name: "sessions/12345",
        state: "IN_PROGRESS",
      };
      const result = parseJulesSession(input);
      expect(result.id).toBe("12345");
      expect(result.status).toBe("IN_PROGRESS");
    });

    it("should use raw name as ID if 'sessions/' prefix is absent", () => {
      const input = {
        name: "custom-session-id",
        state: "SUCCEEDED",
      };
      expect(parseJulesSession(input).id).toBe("custom-session-id");
    });

    it("should default name/id to empty string if missing", () => {
      expect(parseJulesSession({}).id).toBe("");
    });

    it("should map states to COMPLETED, FAILED, IN_PROGRESS, or fallback PENDING", () => {
      expect(parseJulesSession({ state: "SUCCEEDED" }).status).toBe("COMPLETED");
      expect(parseJulesSession({ state: "COMPLETED" }).status).toBe("COMPLETED");

      expect(parseJulesSession({ state: "FAILED" }).status).toBe("FAILED");
      expect(parseJulesSession({ state: "CANCELLED" }).status).toBe("FAILED");
      expect(parseJulesSession({ state: "TERMINATED" }).status).toBe("FAILED");

      expect(parseJulesSession({ state: "IN_PROGRESS" }).status).toBe("IN_PROGRESS");

      expect(parseJulesSession({ state: "UNKNOWN_STATE" }).status).toBe("PENDING");
      expect(parseJulesSession({}).status).toBe("PENDING");
    });

    it("should extract pullRequestUrl from outputs array when present", () => {
      const input = {
        name: "sessions/abc",
        outputs: [
          { type: "text", text: "logs" },
          { pullRequest: { url: "https://github.com/arii/boomtick/pull/100" } },
        ],
      };
      const session = parseJulesSession(input);
      expect(session.pullRequestUrl).toBe("https://github.com/arii/boomtick/pull/100");
    });

    it("should return undefined pullRequestUrl if missing or invalid outputs", () => {
      expect(parseJulesSession({ outputs: [] }).pullRequestUrl).toBeUndefined();
      expect(parseJulesSession({ outputs: [{ other: "data" }] }).pullRequestUrl).toBeUndefined();
      expect(parseJulesSession({ outputs: "not-an-array" }).pullRequestUrl).toBeUndefined();
    });

    it("should parse createTime or fallback to current date", () => {
      const timeStr = "2025-01-01T12:00:00Z";
      const sessionWithTime = parseJulesSession({ createTime: timeStr });
      expect(sessionWithTime.createdAt).toEqual(new Date(timeStr));

      const sessionWithoutTime = parseJulesSession({});
      expect(sessionWithoutTime.createdAt).toBeInstanceOf(Date);
    });
  });
});
