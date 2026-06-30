import { describe, it, expect, vi } from "vitest";
import { createIssueHandler } from "./github.create_issue.js";
import * as shell from "../lib/shell.js";

vi.mock("../lib/shell.js", () => ({
  runCommand: vi.fn()
}));

describe("github.create_issue", () => {
  it("should create an issue successfully", async () => {
    const mockResponse = {
      status: "success",
      issue: {
        number: 123,
        title: "Test Issue",
        html_url: "https://github.com/owner/repo/issues/123",
        state: "open"
      }
    };

    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify(mockResponse),
      stderr: "",
      exitCode: 0,
      durationMs: 10,
      command: "td-cli gh create-issue --title 'Test Issue' --body 'Test Body'"
    });

    const result = await createIssueHandler({ title: "Test Issue", body: "Test Body", file: null });
    expect(result.status).toBe("success");
    expect(result.issue?.number).toBe(123);
    expect(result.issue?.title).toBe("Test Issue");
  });

  it("should throw error on command failure", async () => {
    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: "",
      stderr: "Auth failed",
      exitCode: 1,
      durationMs: 10,
      command: "td-cli gh create-issue"
    });

    await expect(createIssueHandler({ title: "Test Issue", body: "Test Body", file: null })).rejects.toThrow("Failed to create issue: Auth failed");
  });

  it("should handle error status from CLI output", async () => {
    const mockResponse = {
      status: "error",
      message: "Repo not found"
    };

    vi.mocked(shell.runCommand).mockResolvedValue({
      stdout: JSON.stringify(mockResponse),
      stderr: "",
      exitCode: 0,
      durationMs: 10,
      command: "td-cli gh create-issue"
    });

    await expect(createIssueHandler({ title: "Test Issue", body: "Test Body", file: null })).rejects.toThrow("Failed to create issue: Repo not found");
  });
});
