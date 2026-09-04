import { describe, it, expect } from "vitest";
import { createSuccessResult, createErrorResult } from "./result.js";

describe("result utils", () => {
  describe("createSuccessResult", () => {
    it("should format string data directly without JSON stringifying", () => {
      const result = createSuccessResult("simple string message");
      expect(result).toEqual({
        content: [
          {
            type: "text",
            text: "simple string message",
          },
        ],
      });
      expect(result.isError).toBeUndefined();
    });

    it("should format object data as pretty-printed JSON string", () => {
      const objData = { foo: "bar", count: 42 };
      const result = createSuccessResult(objData);
      expect(result).toEqual({
        content: [
          {
            type: "text",
            text: JSON.stringify(objData, null, 2),
          },
        ],
      });
      expect(result.isError).toBeUndefined();
    });
  });

  describe("createErrorResult", () => {
    it("should format error result with message and isError set to true", () => {
      const result = createErrorResult("Something went wrong");
      expect(result).toEqual({
        content: [
          {
            type: "text",
            text: "Something went wrong",
          },
        ],
        isError: true,
      });
    });
  });
});
