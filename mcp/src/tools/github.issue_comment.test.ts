import { beforeEach, describe, expect, it, vi } from "vitest";
import { issueCommentHandler, IssueCommentInputSchema } from "./github.issue_comment.js";
import * as tdCli from "../lib/tdCli.js";
import * as git from "../lib/git.js";

vi.mock("../lib/tdCli.js", () => ({ runTDCli: vi.fn() }));
vi.mock("../lib/git.js", () => ({
  resolveRepo: vi.fn((repo?: string | null) =>
    repo && repo.trim().length > 0 ? repo.trim() : "owner/repo"
  ),
}));

const runTDCli = vi.mocked(tdCli.runTDCli);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("github.issue_comment", () => {
  it("posts a comment with the fallback repo", async () => {
    runTDCli.mockResolvedValue({
      status: "success",
      comment: { id: 555, html_url: "https://github.com/owner/repo/issues/5#issuecomment-555", body: "hi" },
    });

    const result = await issueCommentHandler({ issueNumber: 5, body: "hi" });

    expect(runTDCli).toHaveBeenCalledWith(
      ["gh", "issue-comment", "5", "--body", "hi", "--repo", "owner/repo"],
      "post comment"
    );
    expect(result.status).toBe("success");
    expect(result.comment?.id).toBe(555);
  });

  it("forwards an explicit repo override", async () => {
    runTDCli.mockResolvedValue({ status: "success" });

    await issueCommentHandler({ issueNumber: 5, body: "hi", repo: "org/other" });

    expect(runTDCli).toHaveBeenCalledWith(
      ["gh", "issue-comment", "5", "--body", "hi", "--repo", "org/other"],
      "post comment"
    );
  });

  it("rejects an empty comment body at the schema boundary", () => {
    expect(() => IssueCommentInputSchema.parse({ issueNumber: 5, body: "" })).toThrow(
      /Comment body cannot be empty/
    );
  });

  it("propagates td failure detail instead of 'Unknown error'", async () => {
    runTDCli.mockRejectedValue(new Error("Failed to post comment: Permission denied"));

    await expect(issueCommentHandler({ issueNumber: 5, body: "hi" })).rejects.toThrow(
      /Permission denied/
    );
  });
});

describe("github.issue_comment — #1025 regression: explicit null args", () => {
  it("accepts a null repo and resolves the fallback", async () => {
    runTDCli.mockResolvedValue({ status: "success" });

    await issueCommentHandler({ issueNumber: 5, body: "hi", repo: null });

    expect(runTDCli).toHaveBeenCalledWith(
      ["gh", "issue-comment", "5", "--body", "hi", "--repo", "owner/repo"],
      "post comment"
    );
  });
});
