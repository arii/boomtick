import { beforeEach, describe, expect, it, vi } from "vitest";
import { getPrHandler } from "./github.get_pr.js";
import * as tdCli from "../lib/tdCli.js";
import * as git from "../lib/git.js";
import * as shell from "../lib/shell.js";

vi.mock("../lib/tdCli.js", () => ({ runTDCli: vi.fn() }));
vi.mock("../lib/git.js", () => ({
  resolveRepo: vi.fn((repo?: string | null) =>
    repo && repo.trim().length > 0 ? repo.trim() : "owner/repo"
  ),
  getMergeConflictFiles: vi.fn(),
}));
vi.mock("../lib/shell.js", () => ({ runCommand: vi.fn() }));

const runTDCli = vi.mocked(tdCli.runTDCli);
const getMergeConflictFiles = vi.mocked(git.getMergeConflictFiles);
const runCommand = vi.mocked(shell.runCommand);

beforeEach(() => {
  vi.clearAllMocks();
  getMergeConflictFiles.mockResolvedValue([]);
});

describe("github.get_pr — search mode (no prNumber)", () => {
  it("lists open PRs with defaults", async () => {
    runTDCli.mockResolvedValue({ prs: [{ number: 1 }] });

    const result = await getPrHandler({});

    expect(runTDCli).toHaveBeenCalledWith(
      ["gh", "search-prs", "--state", "open", "--limit", "100", "--repo", "owner/repo"],
      "list PRs"
    );
    expect(result.prs).toEqual([{ number: 1 }]);
  });

  it("forwards state, limit, draft and label filters", async () => {
    runTDCli.mockResolvedValue({ prs: [] });

    await getPrHandler({
      state: "closed",
      limit: 10,
      includeDrafts: false,
      labels: ["bug", "ui"],
    });

    const args = runTDCli.mock.calls[0][0];
    expect(args).toContain("--state");
    expect(args).toContain("closed");
    expect(args).toContain("--limit");
    expect(args).toContain("10");
    expect(args).toContain("--no-include-drafts");
    expect(args).toContain("--labels");
    expect(args).toContain("bug,ui");
  });

  it("omits draft and label flags when unset", async () => {
    runTDCli.mockResolvedValue({ prs: [] });

    await getPrHandler({ state: "all", limit: 5 });

    const args = runTDCli.mock.calls[0][0];
    expect(args).not.toContain("--no-include-drafts");
    expect(args).not.toContain("--labels");
  });
});

describe("github.get_pr — view mode", () => {
  it("views a PR by number with the resolved repo", async () => {
    runTDCli.mockResolvedValue({ pr: { number: 42, title: "Fix" } });

    const result = await getPrHandler({ prNumber: 42, repo: "org/other" });

    expect(runTDCli).toHaveBeenCalledWith(
      ["gh", "view", "42", "--repo", "org/other"],
      "get PR details"
    );
    expect(result.pr).toEqual({ number: 42, title: "Fix" });
  });

  it("absorbs github_get_pr_diff via includeDiff", async () => {
    runTDCli
      .mockResolvedValueOnce({ pr: { number: 42 } })
      .mockResolvedValueOnce({ files: ["a.ts"], diffText: "---", isTruncated: true });

    const result = await getPrHandler({ prNumber: 42, includeDiff: true });

    expect(runTDCli).toHaveBeenNthCalledWith(
      2,
      ["gh", "pr-diff", "42", "--repo", "owner/repo"],
      "get PR diff"
    );
    expect(result.diff).toEqual({ files: ["a.ts"], diffText: "---", isTruncated: true });
  });

  it("absorbs github_get_pr_reviews via includeReviews", async () => {
    runTDCli
      .mockResolvedValueOnce({ pr: { number: 42 } })
      .mockResolvedValueOnce({ reviews: [{ state: "APPROVED" }], review_count: 1 });

    const result = await getPrHandler({ prNumber: 42, includeReviews: true });

    expect(runTDCli).toHaveBeenNthCalledWith(
      2,
      ["gh", "read-pr-reviews", "--pr-number", "42", "--repo", "owner/repo"],
      "read PR reviews"
    );
    expect(result.reviews).toEqual([{ state: "APPROVED" }]);
    expect(result.reviewCount).toBe(1);
  });

  it("absorbs github_get_pr_commits via includeCommits", async () => {
    runTDCli
      .mockResolvedValueOnce({ pr: { number: 42 } })
      .mockResolvedValueOnce({ commits: [{ sha: "abc" }] });

    const result = await getPrHandler({ prNumber: 42, includeCommits: true });

    expect(runTDCli).toHaveBeenNthCalledWith(
      2,
      ["gh", "list-pr-commits", "--pr-number", "42", "--repo", "owner/repo"],
      "list PR commits"
    );
    expect(result.commits).toEqual([{ sha: "abc" }]);
  });
});

describe("github.get_pr — conflict detection (absorbs github_get_merge_conflict_files)", () => {
  it("uses explicit baseBranch and headRef without consulting gh", async () => {
    runTDCli.mockResolvedValue({ pr: { number: 42 } });
    getMergeConflictFiles.mockResolvedValue(["src/conflict.ts"]);

    const result = await getPrHandler({
      prNumber: 42,
      includeConflicts: true,
      baseBranch: "main",
      headRef: "feature",
    });

    expect(getMergeConflictFiles).toHaveBeenCalledWith("main", "feature");
    expect(runCommand).not.toHaveBeenCalled();
    expect(result.conflictFiles).toEqual(["src/conflict.ts"]);
  });

  it("resolves head and base refs from gh pr view when omitted", async () => {
    runTDCli.mockResolvedValue({ pr: { number: 42 } });
    runCommand.mockResolvedValue({
      stdout: JSON.stringify({ headRefName: "feature", baseRefName: "develop" }),
      stderr: "",
      exitCode: 0,
      durationMs: 5,
      command: "gh pr view 42",
    });
    getMergeConflictFiles.mockResolvedValue([]);

    await getPrHandler({ prNumber: 42, includeConflicts: true });

    expect(runCommand).toHaveBeenCalledWith(
      "gh",
      ["pr", "view", "42", "--json", "headRefName,baseRefName", "--repo", "owner/repo"]
    );
    expect(getMergeConflictFiles).toHaveBeenCalledWith("develop", "feature");
  });

  it("falls back to main/HEAD when the gh metadata call fails", async () => {
    runTDCli.mockResolvedValue({ pr: { number: 42 } });
    runCommand.mockResolvedValue({
      stdout: "",
      stderr: "gh: Not Found",
      exitCode: 1,
      durationMs: 5,
      command: "gh pr view 42",
    });

    await getPrHandler({ prNumber: 42, includeConflicts: true });

    expect(getMergeConflictFiles).toHaveBeenCalledWith("main", "HEAD");
  });

  it("keeps the default base when only headRefName resolves", async () => {
    runTDCli.mockResolvedValue({ pr: { number: 42 } });
    runCommand.mockResolvedValue({
      stdout: JSON.stringify({ headRefName: "feature" }),
      stderr: "",
      exitCode: 0,
      durationMs: 5,
      command: "gh pr view 42",
    });

    await getPrHandler({ prNumber: 42, includeConflicts: true });

    expect(getMergeConflictFiles).toHaveBeenCalledWith("main", "feature");
  });
});

describe("github.get_pr — error surfacing", () => {
  it("propagates td failure detail instead of collapsing to 'Unknown error'", async () => {
    runTDCli.mockRejectedValue(new Error("Failed to get PR details: Not Found"));

    await expect(getPrHandler({ prNumber: 42 })).rejects.toThrow(/Not Found/);
    await expect(getPrHandler({ prNumber: 42 })).rejects.not.toThrow(/Unknown error/);
  });
});

describe("github.get_pr — #1025 regression: explicit null args", () => {
  it("accepts null for every optional field and takes the search default path", async () => {
    runTDCli.mockResolvedValue({ prs: [] });

    const result = await getPrHandler({
      prNumber: null,
      repo: null,
      includeDiff: null,
      includeReviews: null,
      includeCommits: null,
      includeConflicts: null,
      baseBranch: null,
      headRef: null,
      state: null,
      includeDrafts: null,
      limit: null,
      labels: null,
    });

    expect(runTDCli).toHaveBeenCalledWith(
      ["gh", "search-prs", "--state", "open", "--limit", "100", "--repo", "owner/repo"],
      "list PRs"
    );
    expect(result.prs).toEqual([]);
  });

  it("treats null prNumber as search mode while honoring the repo override", async () => {
    runTDCli.mockResolvedValue({ pr: { number: 7 } });

    await getPrHandler({ prNumber: null, repo: "org/other" });

    // null prNumber falls into search mode (prNumber == null) — the LLM
    // asked to omit it — and the repo override is still honored.
    expect(runTDCli).toHaveBeenCalledWith(
      expect.arrayContaining(["--repo", "org/other"]),
      "list PRs"
    );
  });

  it("treats null includeConflicts flags as absent", async () => {
    runTDCli.mockResolvedValue({ pr: { number: 42 } });

    const result = await getPrHandler({
      prNumber: 42,
      includeDiff: null,
      includeReviews: null,
      includeCommits: null,
      includeConflicts: null,
      baseBranch: null,
      headRef: null,
    });

    expect(getMergeConflictFiles).not.toHaveBeenCalled();
    expect(result).toEqual({ pr: { number: 42 } });
  });
});
