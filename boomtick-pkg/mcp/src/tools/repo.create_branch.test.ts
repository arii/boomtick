import { describe, it, expect, vi, beforeEach } from "vitest";
import { createBranchHandler, CreateBranchInputSchema } from "./repo.create_branch.js";
import * as shell from "../lib/shell.js";

vi.mock("../lib/shell.js", () => ({
  runCommand: vi.fn(),
}));

describe("repo.create_branch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should create a new branch from a base branch", async () => {
    const args = {
      branchName: "new-feature",
      baseBranch: "main",
    };

    (shell.runCommand as any).mockResolvedValue({ exitCode: 0, stdout: "", stderr: "" });

    const result = await createBranchHandler(args);

    expect(shell.runCommand).toHaveBeenCalledWith("git", ["fetch", "origin", "main"]);
    expect(shell.runCommand).toHaveBeenCalledWith("git", ["checkout", "-b", "new-feature", "origin/main"]);
    expect(result).toEqual({
      success: true,
      branchName: "new-feature",
      baseBranch: "main",
    });
  });

  it("should use default base branch 'main' if not provided", async () => {
    const args = {
      branchName: "another-feature",
    };

    (shell.runCommand as any).mockResolvedValue({ exitCode: 0, stdout: "", stderr: "" });

    const result = await createBranchHandler(args);

    expect(shell.runCommand).toHaveBeenCalledWith("git", ["fetch", "origin", "main"]);
    expect(shell.runCommand).toHaveBeenCalledWith("git", ["checkout", "-b", "another-feature", "origin/main"]);
  });

  it("should throw error if git command fails", async () => {
    const args = {
      branchName: "fail-branch",
    };

    (shell.runCommand as any).mockResolvedValue({ exitCode: 1, stdout: "", stderr: "Error creating branch" });

    await expect(createBranchHandler(args)).rejects.toThrow("Failed to create branch fail-branch: Error creating branch");
  });
});
