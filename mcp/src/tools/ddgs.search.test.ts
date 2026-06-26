import { describe, it, expect, vi, beforeEach } from "vitest";
import { ddgsSearchHandler } from "./ddgs.search.js";
import { runCommand } from "../lib/shell.js";

vi.mock("../lib/shell.js");

describe("ddgsSearchHandler", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("should parse arguments, sanitize query, and return search results", async () => {
    const mockOutput = JSON.stringify([
      { title: "Result 1", href: "https://example.com/1", body: "Description 1" },
      { title: "Result 2", href: "https://example.com/2", body: "Description 2" },
    ]);

    vi.mocked(runCommand).mockResolvedValue({
      stdout: mockOutput,
      stderr: "",
      exitCode: 0,
      durationMs: 100,
      command: "mock python3",
    });

    const result = await ddgsSearchHandler({ query: "test\nquery\x00", maxResults: 2 });

    expect(runCommand).toHaveBeenCalledTimes(1);
    expect(runCommand).toHaveBeenCalledWith(
      "python3",
      [expect.stringContaining("ddgs_search.py"), "test query", "2"]
    );
    expect(result.results).toHaveLength(2);
    expect(result.results[0].title).toBe("Result 1");
  });

  it("should handle raw error when python script exits with non-zero code and non-JSON output", async () => {
    vi.mocked(runCommand).mockResolvedValue({
      stdout: "",
      stderr: "Python script failed",
      exitCode: 1,
      durationMs: 100,
      command: "mock python3",
    });

    await expect(ddgsSearchHandler({ query: "test query", maxResults: 2 })).rejects.toThrow(
      "Failed to search ddgs: Python script failed"
    );
  });

  it("should handle parsed JSON error when python script exits with non-zero code", async () => {
    vi.mocked(runCommand).mockResolvedValue({
      stdout: "",
      stderr: JSON.stringify({ error: "Structured JSON error" }),
      exitCode: 1,
      durationMs: 100,
      command: "mock python3",
    });

    await expect(ddgsSearchHandler({ query: "test query", maxResults: 2 })).rejects.toThrow(
      "Failed to search ddgs: Structured JSON error"
    );
  });

  it("should handle error when python output is not an array", async () => {
    vi.mocked(runCommand).mockResolvedValue({
      stdout: JSON.stringify({ error: "Something went wrong" }),
      stderr: "",
      exitCode: 0,
      durationMs: 100,
      command: "mock python3",
    });

    await expect(ddgsSearchHandler({ query: "test query", maxResults: 2 })).rejects.toThrow(
      "Expected an array of search results"
    );
  });

  it("should handle error when python output cannot be parsed", async () => {
    vi.mocked(runCommand).mockResolvedValue({
      stdout: "invalid json",
      stderr: "",
      exitCode: 0,
      durationMs: 100,
      command: "mock python3",
    });

    await expect(ddgsSearchHandler({ query: "test query", maxResults: 2 })).rejects.toThrow(
      "Failed to parse ddgs search results"
    );
  });
});
