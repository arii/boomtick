import { describe, expect, it, vi, beforeEach } from "vitest";
import { getChangedFiles, getMergeConflictFiles, resolveRepoPath, createWorktree } from "./git.js";
import * as shell from "./shell.js";

vi.mock("./shell.js", () => ({
  runCommand: vi.fn(),
}));

describe("Git Helpers", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  describe("getChangedFiles", () => {
    it("should parse null-delimited git diff output correctly", async () => {
      // Mock git diff output with null character delimiters:
      // Status M -> file1.txt
      // Status A -> file2.txt
      // Status R100 -> old.txt -> new.txt
      const mockStdout = "M\0file1.txt\0A\0file2.txt\0R100\0old.txt\0new.txt\0";
      vi.mocked(shell.runCommand).mockResolvedValueOnce({
        exitCode: 0,
        stdout: mockStdout,
        stderr: "",
        durationMs: 10,
        command: "git diff --name-status -z main...HEAD",
      });

      const result = await getChangedFiles("main", "HEAD");

      expect(shell.runCommand).toHaveBeenCalledWith(
        "git",
        ["diff", "--name-status", "-z", "main...HEAD"],
        { cwd: undefined }
      );
      expect(result).toEqual([
        { status: "M", path: "file1.txt" },
        { status: "A", path: "file2.txt" },
        { status: "R100", path: "new.txt", oldPath: "old.txt" },
      ]);
    });

    it("should throw error if git diff fails", async () => {
      vi.mocked(shell.runCommand).mockResolvedValueOnce({
        exitCode: 1,
        stdout: "",
        stderr: "fatal: bad revision",
        durationMs: 10,
        command: "git diff --name-status -z invalid...HEAD",
      });

      await expect(getChangedFiles("invalid", "HEAD")).rejects.toThrow(
        "Failed to get changed files: fatal: bad revision"
      );
    });
  });

  describe("getMergeConflictFiles", () => {
    it("should parse git merge-tree output when conflicts exist", async () => {
      // Output with 40-char tree hash followed by conflicting filenames
      const mockStdout =
        "5d71843ed2e051b2be91361db7bea0fc4ee1e5a0\nfile1.txt\nsrc/file2.ts\n";
      vi.mocked(shell.runCommand).mockResolvedValueOnce({
        exitCode: 1, // merge-tree exits 1 on conflicts
        stdout: mockStdout,
        stderr: "",
        durationMs: 10,
        command: "git merge-tree --write-tree --name-only main feature",
      });

      const conflicts = await getMergeConflictFiles("main", "feature");

      expect(shell.runCommand).toHaveBeenCalledWith(
        "git",
        ["merge-tree", "--write-tree", "--name-only", "main", "feature"],
        { cwd: undefined }
      );
      expect(conflicts).toEqual(["file1.txt", "src/file2.ts"]);
    });

    it("should return empty array when no conflicts exist", async () => {
      const mockStdout = "5d71843ed2e051b2be91361db7bea0fc4ee1e5a0\n";
      vi.mocked(shell.runCommand).mockResolvedValueOnce({
        exitCode: 0,
        stdout: mockStdout,
        stderr: "",
        durationMs: 10,
        command: "git merge-tree --write-tree --name-only main feature",
      });

      const conflicts = await getMergeConflictFiles("main", "feature");

      expect(conflicts).toEqual([]);
    });

    it("should throw error if git merge-tree exits with unexpected exit code", async () => {
      vi.mocked(shell.runCommand).mockResolvedValueOnce({
        exitCode: 128,
        stdout: "",
        stderr: "fatal: not a valid object name",
        durationMs: 10,
        command: "git merge-tree --write-tree --name-only invalid feature",
      });

      await expect(getMergeConflictFiles("invalid", "feature")).rejects.toThrow(
        "Git merge-tree failed: fatal: not a valid object name"
      );
    });
  });

  describe("resolveRepoPath", () => {
    it("should return explicit path when path is provided", () => {
      const resolved = resolveRepoPath({ path: "/tmp/custom-repo" });
      expect(resolved).toBe("/tmp/custom-repo");
    });

    it("should return explicit repoPath when repoPath is provided", () => {
      const resolved = resolveRepoPath({ repoPath: "/tmp/another-repo" });
      expect(resolved).toBe("/tmp/another-repo");
    });

    it("should resolve repo path via ecosystem_repos when repo is given", () => {
      const resolved = resolveRepoPath({ repo: "arii/tech-dancer" });
      expect(resolved).toContain("tech-dancer");
    });

    it("should fall back to current working directory when empty", () => {
      const resolved = resolveRepoPath({});
      expect(typeof resolved).toBe("string");
      expect(resolved.length).toBeGreaterThan(0);
    });
  });

  describe("createWorktree", () => {
    it("should pass baseRepoPath cwd to runCommand when provided", async () => {
      vi.mocked(shell.runCommand).mockResolvedValue({
        exitCode: 0,
        stdout: "",
        stderr: "",
        durationMs: 5,
        command: "git",
      });

      const worktree = await createWorktree("origin/feature", 123, "/home/ari/tech-dancer");

      expect(worktree).toContain("boomtick-mcp-rescue-123");
      expect(shell.runCommand).toHaveBeenCalledWith(
        "git",
        expect.arrayContaining(["worktree", "add"]),
        { cwd: "/home/ari/tech-dancer" }
      );
    });
  });
});
