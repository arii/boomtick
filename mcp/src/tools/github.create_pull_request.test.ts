import { describe, it, expect, vi } from "vitest";
import { createPullRequestHandler } from "./github.create_pull_request.js";
import * as shell from "../lib/shell.js";

vi.mock("../lib/shell.js", () => ({
  runCommand: vi.fn()
}));

describe("github.create_pull_request", () => {
  it("should create a pull request successfully", async () => {
    const mockResponse = {
      status: "success",
      pr: {
        number: 789,
        html_url: "https://github.com/owner/repo/pull/789"
      }
    };

    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify(mockResponse),
      stderr: "",
      exitCode: 0,
      durationMs: 10,
      command: "td-cli gh create-pr --title 'PR' --body 'Body' --head 'feature' --base 'main'"
    });

    const result = await createPullRequestHandler({
      title: "PR",
      body: "Body",
      head: "feature",
      base: "main",
      draft: false
    });

    expect(result.success).toBe(true);
    expect(result.url).toBe("https://github.com/owner/repo/pull/789");
  });

  it("should append --repo flag when repo parameter is provided", async () => {
    const mockResponse = {
      status: "success",
      pr: {
        number: 999,
        html_url: "https://github.com/org/other-repo/pull/999"
      }
    };

    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify(mockResponse),
      stderr: "",
      exitCode: 0,
      durationMs: 10,
      command: "td-cli gh create-pr --title 'PR' --body 'Body' --head 'feature' --base 'main' --repo 'org/other-repo'"
    });

    const result = await createPullRequestHandler({
      title: "PR",
      body: "Body",
      head: "feature",
      base: "main",
      draft: false,
      repo: "org/other-repo"
    });

    expect(shell.runCommand).toHaveBeenCalledWith("td-cli", [
      "gh",
      "create-pr",
      "--title",
      "PR",
      "--body",
      "Body",
      "--head",
      "feature",
      "--base",
      "main",
      "--repo",
      "org/other-repo"
    ]);
    expect(result.success).toBe(true);
    expect(result.url).toBe("https://github.com/org/other-repo/pull/999");
  });

  it("should throw error on CLI error response", async () => {
    const mockResponse = {
      status: "error",
      message: "Branch not found"
    };

    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify(mockResponse),
      stderr: "",
      exitCode: 0,
      durationMs: 10,
      command: "td-cli gh create-pr"
    });

    await expect(createPullRequestHandler({
      title: "PR",
      body: "Body",
      head: "feature",
      base: "main",
      draft: false
    })).rejects.toThrow("Failed to create pull request: Branch not found");
  });
});
