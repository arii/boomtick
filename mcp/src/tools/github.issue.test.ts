import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../lib/tdCli.js", () => ({ runTDCli: vi.fn() }));

import * as tdCliModule from "../lib/tdCli.js";
import { githubIssueHandler } from "./github.issue.js";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyRecord = Record<string, any>;

const tdMock = () => vi.mocked(tdCliModule.runTDCli);

describe("github_issue mode routing", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("routes an issue-only call to td gh issue-view and returns a typed issue", async () => {
    tdMock().mockResolvedValueOnce({
      issue: { number: 5, title: "T", body: "b", state: "open", html_url: "u" },
    });

    const res = await githubIssueHandler({ issueNumber: 5, repo: "o/r" });

    expect(tdMock()).toHaveBeenCalledWith(
      ["gh", "issue-view", "5", "--repo", "o/r"],
      "view issue",
    );
    expect(res.status).toBe("success");
    expect(res.issue).toEqual({ number: 5, title: "T", body: "b", state: "open", htmlUrl: "u" });
    expect(res.comment).toBeNull();
  });

  it("routes a body/label/state call to td gh issue-update with the flags in order", async () => {
    tdMock().mockResolvedValueOnce({
      issue: { number: 9, title: "T", state: "closed", html_url: null },
    });

    const res = await githubIssueHandler({
      issueNumber: 9,
      repo: "o/r",
      setBody: "new body",
      addLabels: ["a", "b"],
      removeLabels: ["c"],
      state: "closed",
    });

    expect(tdMock()).toHaveBeenCalledWith(
      [
        "gh", "issue-update", "9",
        "--body", "new body",
        "--add-labels", "a,b",
        "--remove-labels", "c",
        "--state", "closed",
        "--repo", "o/r",
      ],
      "update issue",
    );
    expect((res.issue as AnyRecord).state).toBe("closed");
    expect(res.comment).toBeNull();
  });

  it("routes a comment call to td gh issue-comment and returns the comment", async () => {
    tdMock().mockResolvedValueOnce({
      comment: { id: 1, html_url: "u", body: "hi", user: { login: "o" }, created_at: "t", updated_at: "t" },
    });

    const res = await githubIssueHandler({ issueNumber: 3, repo: "o/r", comment: "hi" });

    expect(tdMock()).toHaveBeenCalledWith(
      ["gh", "issue-comment", "3", "--body", "hi", "--repo", "o/r"],
      "post comment",
    );
    expect(res.issue).toBeNull();
    expect((res.comment as AnyRecord).body).toBe("hi");
  });

  it("rejects comment combined with an update before any td write", async () => {
    await expect(
      githubIssueHandler({ issueNumber: 3, comment: "hi", setBody: "b" }),
    ).rejects.toThrow(/Exactly one write per call/);
    expect(tdMock()).not.toHaveBeenCalled();
  });

  it("treats an empty addLabels array as a read, not a write", async () => {
    tdMock().mockResolvedValueOnce({ issue: { number: 2, title: "T", state: "open" } });

    await githubIssueHandler({ issueNumber: 2, addLabels: [] });

    expect(tdMock()).toHaveBeenCalledWith(
      ["gh", "issue-view", "2", "--repo", expect.any(String)],
      "view issue",
    );
  });

  it("degrades malformed td payloads to null fields instead of throwing on success", async () => {
    tdMock().mockResolvedValueOnce({ issue: { number: "not-a-number" } });

    const res = await githubIssueHandler({ issueNumber: 8 });

    expect((res.issue as AnyRecord).number).toBe(0);
    expect((res.issue as AnyRecord).title).toBe("");
  });
});
