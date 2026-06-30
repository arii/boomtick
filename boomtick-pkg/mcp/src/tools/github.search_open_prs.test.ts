import { describe, it, expect, vi } from "vitest";
import { searchOpenPrsHandler } from "./github.search_open_prs.js";
import * as shell from "../lib/shell.js";

vi.mock("../lib/shell.js", () => ({
  runCommand: vi.fn()
}));

describe("github.search_open_prs", () => {
  it("should return normalized PR objects", async () => {
    const mockResponse = {
      status: "success",
      prs: [
        { number: 1, title: "Test PR", author: { login: "user" }, isDraft: false }
      ]
    };

    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify(mockResponse),
      stderr: "",
      exitCode: 0,
      durationMs: 10,
      command: "gh pr list"
    });

    const result = await searchOpenPrsHandler({ state: "open", limit: 1, includeDrafts: true });
    expect(result.prs).toHaveLength(1);
    expect(result.prs[0].number).toBe(1);
  });

  it("should handle empty PR list", async () => {
    const mockResponse = {
      status: "success",
      prs: []
    };

    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify(mockResponse),
      stderr: "",
      exitCode: 0,
      durationMs: 10,
      command: "gh pr list"
    });

    const result = await searchOpenPrsHandler({ state: "open", limit: 10, includeDrafts: true });
    expect(result.prs).toHaveLength(0);
  });

  it("should throw error on command failure", async () => {
    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: "",
      stderr: "Auth failed",
      exitCode: 1,
      durationMs: 10,
      command: "gh pr list"
    });

    await expect(searchOpenPrsHandler({ state: "open", limit: 10, includeDrafts: true })).rejects.toThrow("Failed to list PRs: Auth failed");
  });
});
