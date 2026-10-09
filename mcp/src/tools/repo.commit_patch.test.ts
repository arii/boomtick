import { describe, it, expect, vi, beforeEach } from "vitest";
import { parsePorcelainLine, commitPatchHandler } from "./repo.commit_patch.js";
import * as shellModule from "../lib/shell.js";

vi.mock("../lib/shell.js");

describe("repo.commit_patch", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  describe("parsePorcelainLine", () => {
    it("should correctly parse porcelain lines with leading status space without slicing offset bug", () => {
      expect(parsePorcelainLine(" M boomtick-pkg")).toBe("boomtick-pkg");
      expect(parsePorcelainLine("M  src/index.ts")).toBe("src/index.ts");
      expect(parsePorcelainLine("?? env.example")).toBe("env.example");
      expect(parsePorcelainLine(' M "quoted/file.ts"')).toBe("quoted/file.ts");
    });

    it("should return null for invalid lines", () => {
      expect(parsePorcelainLine("")).toBeNull();
      expect(parsePorcelainLine("  ")).toBeNull();
    });
  });

  describe("commitPatchHandler", () => {
    it("should stage only allowed files and commit successfully", async () => {
      const mockRunCommand = vi.spyOn(shellModule, "runCommand");

      mockRunCommand
        .mockResolvedValueOnce({ stdout: " M boomtick-pkg\n", stderr: "", exitCode: 0, durationMs: 10, command: "" }) // status
        .mockResolvedValueOnce({ stdout: "", stderr: "", exitCode: 0, durationMs: 10, command: "" }) // add
        .mockResolvedValueOnce({ stdout: "[main 123456] commit msg", stderr: "", exitCode: 0, durationMs: 10, command: "" }) // commit
        .mockResolvedValueOnce({ stdout: "1234567890abcdef\n", stderr: "", exitCode: 0, durationMs: 10, command: "" }); // rev-parse

      const res = await commitPatchHandler({
        message: "Fix bug",
        allowedFiles: ["boomtick-pkg"],
        writeMode: true,
      });

      expect(res.success).toBe(true);
      expect(res.commitSha).toBe("1234567890abcdef");
      expect(res.changedFiles).toEqual(["boomtick-pkg"]);

      expect(mockRunCommand).toHaveBeenCalledWith("git", ["add", "--", "boomtick-pkg"], expect.any(Object));
    });

    it("should throw error if forbidden file is modified", async () => {
      const mockRunCommand = vi.spyOn(shellModule, "runCommand");

      mockRunCommand.mockResolvedValueOnce({
        stdout: " M boomtick-pkg\n M env.example\n",
        stderr: "",
        exitCode: 0,
        durationMs: 10,
        command: "",
      });

      await expect(
        commitPatchHandler({
          message: "Fix bug",
          allowedFiles: ["boomtick-pkg"],
          writeMode: true,
        })
      ).rejects.toThrow("The following files are not in the allowed list: env.example");
    });
  });
});
