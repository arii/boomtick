import { describe, it, expect, vi } from "vitest";
import path from "path";
import fs from "fs";
import { resolveTdPath, resetTdPathForTests, runCommand } from "./shell.js";

// Simple test to verify environment and vitest setup
describe("Basic Environment", () => {
  it("should have a valid repo path", () => {
    const repoPath = process.env.BOOMTICK_REPO_PATH || "/app";
    expect(repoPath).toBeDefined();
    expect(path.isAbsolute(repoPath)).toBe(true);
  });
});

describe("td binary resolution", () => {
  it("resolves the td path once per process, not per call", () => {
    resetTdPathForTests();
    const spy = vi.spyOn(fs, "existsSync");
    const first = resolveTdPath();
    const callsAfterFirst = spy.mock.calls.length;
    expect(first).toBeTruthy();
    expect(resolveTdPath()).toBe(first);
    expect(resolveTdPath()).toBe(first);
    // Repeat calls add no further filesystem probes.
    expect(spy.mock.calls.length).toBe(callsAfterFirst);
    spy.mockRestore();
    resetTdPathForTests();
  });
});

describe("command allowlist", () => {
  it("rejects destructive/shell commands tools never invoke", async () => {
    for (const cmd of ["rm", "cp", "sh", "ls", "mkdir"]) {
      await expect(runCommand(cmd, [])).rejects.toThrow("Command not allowed");
    }
  });
});
