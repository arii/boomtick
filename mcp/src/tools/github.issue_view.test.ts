import { beforeEach, describe, expect, it, vi } from "vitest";
import { issueViewHandler } from "./github.issue_view.js";
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

describe("github.issue_view", () => {
  it("views an issue with the fallback repo", async () => {
    runTDCli.mockResolvedValue({
      status: "success",
      issue: { number: 7, title: "Broken build", body: "Details", state: "open" },
    });

    const result = await issueViewHandler({ issueNumber: 7 });

    expect(runTDCli).toHaveBeenCalledWith(
      ["gh", "issue-view", "7", "--repo", "owner/repo"],
      "view issue"
    );
    expect(result).toEqual({
      issue: { number: 7, title: "Broken build", body: "Details", state: "open" },
    });
  });

  it("forwards an explicit repo override", async () => {
    runTDCli.mockResolvedValue({ status: "success", issue: { number: 8, title: "Other", state: "open" } });

    await issueViewHandler({ issueNumber: 8, repo: "org/other" });

    expect(runTDCli).toHaveBeenCalledWith(
      ["gh", "issue-view", "8", "--repo", "org/other"],
      "view issue"
    );
  });

  it("accepts a null body from td", async () => {
    runTDCli.mockResolvedValue({
      status: "success",
      issue: { number: 9, title: "T", body: null, state: "open" },
    });

    const result = await issueViewHandler({ issueNumber: 9 });

    expect(result.issue?.body).toBeNull();
  });

  it("fails loud when td returns a malformed issue payload", async () => {
    // Output schema requires state; a malformed td payload must surface as
    // a parse error instead of flowing as a valid-looking response.
    runTDCli.mockResolvedValue({ status: "success", issue: { number: 10 } });

    await expect(issueViewHandler({ issueNumber: 10 })).rejects.toThrow();
  });

  it("propagates td failure detail instead of 'Unknown error'", async () => {
    runTDCli.mockRejectedValue(new Error("Failed to view issue: Not Found"));

    await expect(issueViewHandler({ issueNumber: 7 })).rejects.toThrow(/Not Found/);
  });
});

describe("github.issue_view — #1025 regression: explicit null args", () => {
  it("accepts a null repo and resolves the fallback", async () => {
    runTDCli.mockResolvedValue({ status: "success", issue: { number: 7, title: "T", state: "open" } });

    await issueViewHandler({ issueNumber: 7, repo: null });

    expect(runTDCli).toHaveBeenCalledWith(
      ["gh", "issue-view", "7", "--repo", "owner/repo"],
      "view issue"
    );
  });
});
