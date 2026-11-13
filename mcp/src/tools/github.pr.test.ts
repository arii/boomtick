import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../lib/tdCli.js", () => ({ runTDCli: vi.fn() }));
vi.mock("../lib/shell.js", () => ({ runCommand: vi.fn() }));
vi.mock("../lib/git.js", () => ({
  resolveRepo: vi.fn((repo?: string | null) => repo ?? "o/r"),
  getMergeConflictFiles: vi.fn(),
}));

import * as tdCliModule from "../lib/tdCli.js";
import * as shellModule from "../lib/shell.js";
import * as gitModule from "../lib/git.js";
import { githubPrHandler } from "./github.pr.js";

const tdMock = () => vi.mocked(tdCliModule.runTDCli);
const ghMock = () => vi.mocked(shellModule.runCommand);

describe("github_pr mode routing", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("views a PR by default and returns the typed pr payload", async () => {
    tdMock().mockResolvedValueOnce({ pr: { number: 7, title: "T" } });

    const res = await githubPrHandler({ prNumber: 7 });

    expect(tdMock()).toHaveBeenCalledWith(["gh", "view", "7", "--repo", "o/r"], "get PR details");
    expect(res.status).toBe("success");
    expect(res.pr).toEqual({ number: 7, title: "T" });
  });

  it("searches only when the explicit search object is given", async () => {
    tdMock().mockResolvedValueOnce({ prs: [{ number: 1 }, { number: 2 }] });

    const res = await githubPrHandler({ search: { state: "open", labels: ["a", "b"], limit: 50 } });

    expect(tdMock()).toHaveBeenCalledWith(
      ["gh", "search-prs", "--state", "open", "--limit", "50", "--repo", "o/r", "--labels", "a,b"],
      "list PRs",
    );
    expect((res.prs as unknown[]).length).toBe(2);
    expect(res.pr).toBeNull();
  });

  it("rejects a call with neither prNumber nor search", async () => {
    await expect(githubPrHandler({})).rejects.toThrow(/Provide prNumber to view a PR, or search to list PRs/);
  });

  it("appends the diff section when included", async () => {
    tdMock().mockResolvedValueOnce({ pr: { number: 7 } });
    tdMock().mockResolvedValueOnce({ files: ["a.ts"], diffText: "diff", isTruncated: false });

    const res = await githubPrHandler({ prNumber: 7, include: ["diff"] });

    expect(tdMock()).toHaveBeenNthCalledWith(
      2,
      ["gh", "pr-diff", "7", "--repo", "o/r"],
      "get PR diff",
    );
    expect((res.diff as Record<string, unknown>).diffText).toBe("diff");
  });

  it("appends reviews and commits with their td subcommands", async () => {
    tdMock().mockResolvedValueOnce({ pr: { number: 7 } });
    tdMock().mockResolvedValueOnce({ reviews: [{ id: 1 }], review_count: 1 });
    tdMock().mockResolvedValueOnce({ commits: [{ sha: "abc" }] });

    const res = await githubPrHandler({ prNumber: 7, include: ["reviews", "commits"] });

    expect(tdMock()).toHaveBeenNthCalledWith(
      2,
      ["gh", "read-pr-reviews", "--pr-number", "7", "--repo", "o/r"],
      "read PR reviews",
    );
    expect(tdMock()).toHaveBeenNthCalledWith(
      3,
      ["gh", "list-pr-commits", "--pr-number", "7", "--repo", "o/r"],
      "list PR commits",
    );
    expect((res.reviews as unknown[]).length).toBe(1);
    expect(res.reviewCount).toBe(1);
    expect((res.commits as unknown[]).length).toBe(1);
  });

  it("resolves conflict files from the PR's own base and head", async () => {
    tdMock().mockResolvedValueOnce({ pr: { number: 7 } });
    ghMock().mockResolvedValueOnce({
      exitCode: 0,
      stdout: JSON.stringify({ headRefName: "feat", baseRefName: "dev" }),
      stderr: "",
      durationMs: 0,
      command: "gh",
    });
    vi.mocked(gitModule.getMergeConflictFiles).mockResolvedValueOnce(["src/a.ts"]);

    const res = await githubPrHandler({ prNumber: 7, include: ["conflicts"] });

    expect(ghMock()).toHaveBeenCalledWith("gh", [
      "pr", "view", "7", "--json", "headRefName,baseRefName", "--repo", "o/r",
    ]);
    expect(gitModule.getMergeConflictFiles).toHaveBeenCalledWith("dev", "feat");
    expect(res.conflictFiles).toEqual(["src/a.ts"]);
  });

  it("falls back to HEAD when the PR metadata call fails", async () => {
    tdMock().mockResolvedValueOnce({ pr: { number: 7 } });
    ghMock().mockResolvedValueOnce({
      exitCode: 1,
      stdout: "",
      stderr: "boom",
      durationMs: 0,
      command: "gh",
    });
    vi.mocked(gitModule.getMergeConflictFiles).mockResolvedValueOnce([]);

    await githubPrHandler({ prNumber: 7, include: ["conflicts"] });

    expect(gitModule.getMergeConflictFiles).toHaveBeenCalledWith("main", "HEAD");
  });

  it("serves ciLogs through the absorbed repo_read_ci_logs path", async () => {
    tdMock().mockResolvedValueOnce({ pr: { number: 7 } });
    tdMock().mockResolvedValueOnce({ checks: [], failedChecks: ["lint"], logs: "log text" });

    const res = await githubPrHandler({ prNumber: 7, include: ["ciLogs"] });

    expect(tdMock()).toHaveBeenNthCalledWith(
      2,
      ["repo", "ci-logs", "7", "--repo", "o/r"],
      "fetch CI logs",
    );
    expect((res.ciLogs as Record<string, unknown>).logs).toBe("log text");
    expect((res.ciLogs as Record<string, unknown>).failedChecks).toEqual(["lint"]);
  });

  it("lists workflow runs without a PR number", async () => {
    tdMock().mockResolvedValueOnce({ workflow_runs: [{ id: 1 }] });

    const res = await githubPrHandler({ include: ["workflowRuns"] });

    expect(tdMock()).toHaveBeenCalledWith(["repo", "workflow-runs", "--repo", "o/r"], "fetch workflow runs");
    expect(res.workflowRuns).toEqual([{ id: 1 }]);
    expect(res.pr).toBeNull();
  });
});
