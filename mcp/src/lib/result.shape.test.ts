import { describe, it, expect, expectTypeOf } from "vitest";
import { createSuccessResult } from "./result.js";

// Regression tests for issue #1222 item (2): createSuccessResult used to
// take `data: any`, letting any wrong-shaped payload flow into tool output
// unvalidated. The parameter is now `unknown` and non-record payloads are
// wrapped so structuredContent stays a record.
describe("createSuccessResult payload shape (issue 1222)", () => {
  it("closes the any-hole: the payload parameter is unknown", () => {
    // Red on pre-fix code where the parameter was `any`.
    expectTypeOf(createSuccessResult).parameter(0).toEqualTypeOf<unknown>();
  });

  it("wraps null so structuredContent stays a record", () => {
    const result = createSuccessResult(null);
    expect(result.structuredContent).toEqual({ result: null });
    expect(result.isError).toBeUndefined();
  });

  it("wraps numbers so they do not flow as a bare scalar", () => {
    const result = createSuccessResult(42);
    expect(result.structuredContent).toEqual({ result: 42 });
    expect(result.content).toEqual([{ type: "text", text: "42" }]);
  });

  it("wraps booleans instead of passing them through", () => {
    const result = createSuccessResult(true);
    expect(result.structuredContent).toEqual({ result: true });
  });

  it("passes record payloads through as structuredContent", () => {
    const payload = { status: "success", count: 3 };
    const result = createSuccessResult(payload);
    expect(result.structuredContent).toEqual(payload);
  });
});
