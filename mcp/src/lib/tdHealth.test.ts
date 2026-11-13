import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("child_process", () => ({ spawnSync: vi.fn() }));

// eslint-disable-next-line import/first
import { spawnSync } from "child_process";
import {
  checkTdAvailability,
  recordTdPreflight,
  resetTdPreflightForTests,
} from "./tdHealth.js";
import { getServerHealth } from "../tools/repo.context.js";

type SpawnSyncResult = ReturnType<typeof spawnSync>;

function spawnResult(overrides: Partial<SpawnSyncResult>): SpawnSyncResult {
  return {
    pid: -1,
    output: [null, "", ""],
    signal: null,
    status: null,
    stdout: "",
    stderr: "",
    error: undefined,
    ...overrides,
  };
}

// healthHandler reads config lazily; provide the env it needs when the
// suite runs outside a configured checkout.
process.env.GITHUB_OWNER = process.env.GITHUB_OWNER || "test-owner";
process.env.GITHUB_REPO = process.env.GITHUB_REPO || "test-repo";
process.env.BOOMTICK_REPO_PATH = process.env.BOOMTICK_REPO_PATH || process.cwd();

// Regression tests for audit H4: the startup preflight must be a
// warn-and-continue check, not a process.exit(1).
describe("checkTdAvailability", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetTdPreflightForTests();
  });

  afterEach(() => {
    resetTdPreflightForTests();
  });

  it("reports unavailable with a reason when td is missing from PATH", () => {
    vi.mocked(spawnSync).mockReturnValue(
      spawnResult({ error: new Error("spawnSync td ENOENT") }),
    );

    const result = checkTdAvailability("/tmp");
    expect(result.available).toBe(false);
    expect(result.reason).toContain("not resolvable on PATH");
  });

  it("reports unavailable with the exit code when td doctor fails", () => {
    vi.mocked(spawnSync).mockReturnValue(spawnResult({ status: 3, stderr: "boom" }));

    const result = checkTdAvailability("/tmp");
    expect(result.available).toBe(false);
    expect(result.reason).toContain("exit code: 3");
  });

  it("reports available when td doctor succeeds", () => {
    vi.mocked(spawnSync).mockReturnValue(spawnResult({ status: 0, stdout: "{}" }));

    const result = checkTdAvailability("/tmp");
    expect(result.available).toBe(true);
    expect(result.reason).toBeUndefined();
  });

  it("invokes td doctor with shell disabled in the given cwd", () => {
    vi.mocked(spawnSync).mockReturnValue(spawnResult({ status: 0, stdout: "{}" }));

    checkTdAvailability("/tmp");
    expect(spawnSync).toHaveBeenCalledWith("td", ["doctor"], expect.objectContaining({ cwd: "/tmp", shell: false }));
  });
});

describe("tdAvailable surfaced through repo_context server health", () => {
  beforeEach(() => {
    resetTdPreflightForTests();
  });

  afterEach(() => {
    resetTdPreflightForTests();
  });

  it("is null before the preflight has run", () => {
    const health = getServerHealth();
    expect(health.tdAvailable).toBeNull();
  });

  it("reflects a recorded failed preflight without crashing the handler", () => {
    recordTdPreflight({ available: false, reason: "td is not resolvable on PATH: ENOENT" });
    const health = getServerHealth();
    expect(health.tdAvailable).toBe(false);
  });

  it("reflects a successful preflight", () => {
    recordTdPreflight({ available: true });
    const health = getServerHealth();
    expect(health.tdAvailable).toBe(true);
  });
});
