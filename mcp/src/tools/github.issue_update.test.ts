import { beforeEach, describe, expect, it, vi } from "vitest";
import { issueUpdateHandler } from "./github.issue_update.js";
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

function tdOk() {
  runTDCli.mockResolvedValue({
    status: "success",
    issue: { number: 3, title: "T", state: "closed" },
  });
}

describe("github.issue_update", () => {
  it("passes body, file, labels and state flags through to td", async () => {
    tdOk();

    await issueUpdateHandler({
      issueNumber: 3,
      body: "New body",
      file: "body.md",
      labels: ["a", "b"],
      addLabels: ["c"],
      removeLabels: ["d"],
      state: "closed",
      repo: "org/other",
    });

    expect(runTDCli).toHaveBeenCalledWith(
      [
        "gh", "issue-update", "3",
        "--body", "New body",
        "--file", "body.md",
        "--labels", "a,b",
        "--add-labels", "c",
        "--remove-labels", "d",
        "--state", "closed",
        "--repo", "org/other",
      ],
      "update issue"
    );
  });

  it("omits flags for unset fields", async () => {
    tdOk();

    await issueUpdateHandler({ issueNumber: 3 });

    const args = runTDCli.mock.calls[0][0];
    expect(args).toEqual(["gh", "issue-update", "3", "--repo", "owner/repo"]);
  });

  it("skips empty label arrays", async () => {
    tdOk();

    await issueUpdateHandler({ issueNumber: 3, labels: [], addLabels: [] });

    const args = runTDCli.mock.calls[0][0];
    expect(args).not.toContain("--labels");
    expect(args).not.toContain("--add-labels");
  });

  it("returns the updated issue", async () => {
    tdOk();

    const result = await issueUpdateHandler({ issueNumber: 3, state: "closed" });

    expect(result.status).toBe("success");
    expect(result.issue).toEqual({ number: 3, title: "T", state: "closed" });
  });

  it("propagates td failure detail instead of 'Unknown error'", async () => {
    runTDCli.mockRejectedValue(new Error("Failed to update issue: Permission denied"));

    await expect(issueUpdateHandler({ issueNumber: 3 })).rejects.toThrow(/Permission denied/);
  });
});

describe("github.issue_update — #1025 regression: explicit null args", () => {
  it("accepts null for every optional field", async () => {
    tdOk();

    await issueUpdateHandler({
      issueNumber: 3,
      body: null,
      file: null,
      labels: null,
      addLabels: null,
      removeLabels: null,
      state: null,
      repo: null,
    });

    const args = runTDCli.mock.calls[0][0];
    expect(args).toEqual(["gh", "issue-update", "3", "--repo", "owner/repo"]);
  });
});
