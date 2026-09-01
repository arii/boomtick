import { describe, it, expect } from "vitest";
import { sanitizeError } from "./error_utils.js";

describe("error_utils", () => {
  describe("sanitizeError", () => {
    it("should return 'Unknown error' when stderr is empty", () => {
      expect(sanitizeError("")).toBe("Unknown error");
    });

    it("should return only the first line of stderr", () => {
      const stderr = "Error: Something failed\n  at StackTrace.line1\n  at StackTrace.line2";
      expect(sanitizeError(stderr)).toBe("Error: Something failed");
    });

    it("should truncate lines exceeding 200 characters", () => {
      const longLine = "A".repeat(250);
      const result = sanitizeError(longLine);
      expect(result.length).toBe(200);
      expect(result).toBe("A".repeat(200));
    });

    it("should preserve first line if under 200 characters", () => {
      const line = "Fatal error: unexpected token near line 5";
      expect(sanitizeError(line)).toBe(line);
    });
  });
});
