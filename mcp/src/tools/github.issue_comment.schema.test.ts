import { describe, it, expect, vi, beforeEach, expectTypeOf } from "vitest";
import { issueCommentHandler } from "./github.issue_comment.js";
import type { IssueComment } from "./github.issue_comment.js";
import * as shellModule from "../lib/shell.js";
import type { ShellResult } from "../lib/shell.js";

function tdComment(comment: unknown): ShellResult {
  return {
    exitCode: 0,
    stdout: JSON.stringify({ status: "success", comment }),
    stderr: "",
    durationMs: 0,
    command: "td",
  };
}

const validComment = {
  id: 7,
  html_url: "https://github.com/o/r/issues/1#issuecomment-7",
  body: "hello",
  user: { login: "octo" },
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

// Regression tests for issue #1222 items (2)+(5): the per-tool output
// schema. The comment output used to be `z.any()`, so any wrong-shaped
// payload flowed into the tool result. It must now be rejected loudly.
describe("issue_comment output schema (issue 1222)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("types the comment elements instead of any", () => {
    // Red on pre-fix code where the IssueComment type did not exist.
    expectTypeOf<IssueComment["id"]>().toEqualTypeOf<number | undefined>();
    expectTypeOf<NonNullable<IssueComment["user"]>["login"]>().toEqualTypeOf<string>();
  });

  it("rejects a wrong-typed comment id instead of flowing it through", async () => {
    vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce(
      tdComment({ ...validComment, id: "not-a-number" }),
    );
    await expect(
      issueCommentHandler({ issueNumber: 1, body: "hello" }),
    ).rejects.toThrow();
  });

  it("rejects a non-object comment element", async () => {
    vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce(
      tdComment("just-a-string"),
    );
    await expect(
      issueCommentHandler({ issueNumber: 1, body: "hello" }),
    ).rejects.toThrow();
  });

  it("rejects a wrong-typed nested user element", async () => {
    vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce(
      tdComment({ ...validComment, user: { login: 7 } }),
    );
    await expect(
      issueCommentHandler({ issueNumber: 1, body: "hello" }),
    ).rejects.toThrow();
  });

  it("accepts a missing comment as undefined", async () => {
    vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce(
      tdComment(undefined),
    );
    const res = await issueCommentHandler({ issueNumber: 1, body: "hello" });
    expect(res).toEqual({ status: "success", comment: undefined });
  });

  it("passes a valid comment through typed", async () => {
    vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce(
      tdComment(validComment),
    );
    const res = await issueCommentHandler({ issueNumber: 1, body: "hello" });
    expect(res.status).toBe("success");
    expect(res.comment?.id).toBe(7);
    expect(res.comment?.user?.login).toBe("octo");
  });
});
