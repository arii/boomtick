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

describe("timeout kill escalation", () => {
  it("SIGKILLs a child that ignores SIGTERM after the grace period", async () => {
    // Unique per run so a stale process from an earlier run cannot
    // satisfy the ps assertion.
    const marker = `obvious_hang_${Date.now()}`;
    const start = Date.now();
    await expect(
      runCommand(
        "python3",
        [
          "-c",
          `import signal, time  # ${marker}\n` +
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n" +
            "time.sleep(60)",
        ],
        { timeout: 500 },
      ),
    ).rejects.toThrow("Command timed out");

    // 500ms timeout + 2s SIGKILL grace, with scheduling slack — the
    // SIGKILL lands well after the rejection, so wait out the grace first.
    const elapsed = Date.now() - start;
    expect(elapsed).toBeLessThan(8000);
    await new Promise((resolve) => setTimeout(resolve, 2500));
    const { execSync } = await import("child_process");
    const ps = execSync("ps -eo args", { encoding: "utf-8" });
    expect(ps).not.toContain(marker);
  }, 15000);
});
