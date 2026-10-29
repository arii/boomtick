import { describe, it, expect, vi, beforeEach } from "vitest";
import { createBranchHandler, CreateBranchInput } from "./repo.create_branch.js";
import * as shell from "../lib/shell.js";

vi.mock("../lib/shell.js", () => ({
  runCommand: vi.fn(),
}));

describe("repo.create_branch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should create a new branch from a base branch", async () => {
    const args: CreateBranchInput = {
      branchName: "new-feature",
      baseBranch: "main",
    };

    (shell.runCommand as any).mockResolvedValue({ exitCode: 0, stdout: "", stderr: "" });

    const result = await createBranchHandler(args);

    expect(shell.runCommand).toHaveBeenCalledWith(
      "git",
      ["fetch", "origin", "main"],
      { cwd: expect.any(String) }
    );
    expect(shell.runCommand).toHaveBeenCalledWith(
      "git",
      ["checkout", "-b", "new-feature", "origin/main"],
      { cwd: expect.any(String) }
    );
    expect(result).toMatchObject({
      success: true,
      branchName: "new-feature",
      baseBranch: "main",
    });
    expect(result.path).toBeDefined();
  });

  it("should use default base branch 'main' if not provided", async () => {
    const args: CreateBranchInput = {
      branchName: "another-feature",
    };

    (shell.runCommand as any).mockResolvedValue({ exitCode: 0, stdout: "", stderr: "" });

    const result = await createBranchHandler(args);

    expect(shell.runCommand).toHaveBeenCalledWith(
      "git",
      ["fetch", "origin", "main"],
      { cwd: expect.any(String) }
    );
    expect(shell.runCommand).toHaveBeenCalledWith(
      "git",
      ["checkout", "-b", "another-feature", "origin/main"],
      { cwd: expect.any(String) }
    );
    expect(result.success).toBe(true);
  });

  it("should create branch in specified target workspace path", async () => {
    const args: CreateBranchInput = {
      branchName: "custom-path-feature",
      baseBranch: "main",
      path: "/home/ari/tech-dancer",
    };

    (shell.runCommand as any).mockResolvedValue({ exitCode: 0, stdout: "", stderr: "" });

    const result = await createBranchHandler(args);

    expect(shell.runCommand).toHaveBeenCalledWith(
      "git",
      ["fetch", "origin", "main"],
      { cwd: "/home/ari/tech-dancer" }
    );
    expect(shell.runCommand).toHaveBeenCalledWith(
      "git",
      ["checkout", "-b", "custom-path-feature", "origin/main"],
      { cwd: "/home/ari/tech-dancer" }
    );
    expect(result).toEqual({
      success: true,
      branchName: "custom-path-feature",
      baseBranch: "main",
      path: "/home/ari/tech-dancer",
    });
  });

  it("should include repo field when repo override is specified", async () => {
    const args: CreateBranchInput = {
      branchName: "repo-feature",
      baseBranch: "main",
      repo: "arii/tech-dancer",
      path: "/home/ari/tech-dancer",
    };

    (shell.runCommand as any).mockResolvedValue({ exitCode: 0, stdout: "", stderr: "" });

    const result = await createBranchHandler(args);

    expect(result).toEqual({
      success: true,
      branchName: "repo-feature",
      baseBranch: "main",
      path: "/home/ari/tech-dancer",
      repo: "arii/tech-dancer",
    });
  });

  it("should throw error if git command fails", async () => {
    const args: CreateBranchInput = {
      branchName: "fail-branch",
    };

    (shell.runCommand as any).mockResolvedValue({ exitCode: 1, stdout: "", stderr: "Error creating branch" });

    await expect(createBranchHandler(args)).rejects.toThrow("Failed to create branch fail-branch: Error creating branch");
  });
});
