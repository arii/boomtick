import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { config } from "../config.js";
import { repoTestHandler, RepoTestInputSchema } from "./repo.tests.js";
import * as shell from "../lib/shell.js";

vi.mock("../lib/shell.js", () => ({ runCommand: vi.fn() }));
vi.mock("node:fs/promises", () => ({ readFile: vi.fn() }));
vi.mock("../config.js", () => ({ config: { repoPath: "/repo/configured-root" } }));

const runCommand = vi.mocked(shell.runCommand);

beforeEach(() => {
  vi.clearAllMocks();
});

function ok(command: string): shell.ShellResult {
  return { command, stdout: "done", stderr: "", exitCode: 0, durationMs: 10 };
}

function fail(command: string, stderr = "boom"): shell.ShellResult {
  return { command, stdout: "", stderr, exitCode: 1, durationMs: 10 };
}

// The tokenizer lives unexported inside the handler module, so its behavior
// is verified through the (cmd, args) pairs the handler passes to runCommand.
const commandsSent = (): Array<[string, string[]]> =>
  runCommand.mock.calls.map(([cmd, args]) => [cmd as string, args as string[]]);

describe("repo_test — regex tokenizer", () => {
  it("splits plain space-separated commands", async () => {
    runCommand.mockResolvedValue(ok("pnpm lint"));

    await repoTestHandler({ commands: ["pnpm lint --fix"] });

    expect(commandsSent()).toEqual([["pnpm", ["lint", "--fix"]]]);
  });

  it("keeps double-quoted arguments together and unescapes \\\"", async () => {
    runCommand.mockResolvedValue(ok("node"));

    await repoTestHandler({
      commands: ['node -e "console.log(\\"hello world\\")"'],
    });

    expect(commandsSent()).toEqual([
      ["node", ["-e", 'console.log("hello world")']],
    ]);
  });

  it("keeps single-quoted arguments together", async () => {
    runCommand.mockResolvedValue(ok("grep"));

    await repoTestHandler({ commands: ["grep 'a b c' file.txt"] });

    expect(commandsSent()).toEqual([["grep", ["a b c", "file.txt"]]]);
  });

  it("keeps escaped single quotes inside single-quoted arguments", async () => {
    runCommand.mockResolvedValue(ok("grep"));

    await repoTestHandler({ commands: ["grep 'it\\'s' file.txt"] });

    expect(commandsSent()).toEqual([["grep", ["it's", "file.txt"]]]);
  });

  it("collapses runs of whitespace", async () => {
    runCommand.mockResolvedValue(ok("pnpm"));

    await repoTestHandler({ commands: ["pnpm   test    --run"] });

    expect(commandsSent()).toEqual([["pnpm", ["test", "--run"]]]);
  });
});

describe("repo_test — execution semantics", () => {
  it("runs all four defaults when the target package has lint, test and build scripts", async () => {
    vi.mocked(readFile).mockResolvedValue(JSON.stringify({ scripts: { lint: "eslint .", test: "vitest", build: "tsc" } }));
    runCommand.mockResolvedValue(ok("pnpm"));

    const result = await repoTestHandler({});

    expect(runCommand).toHaveBeenCalledTimes(4);
    expect(commandsSent()[0]).toEqual(["pnpm", ["install", "--frozen-lockfile"]]);
    expect(commandsSent()[3]).toEqual(["pnpm", ["build"]]);
    expect(result.passed).toBe(true);
    expect(result.failedTests).toEqual([]);
    expect(readFile).toHaveBeenCalledWith(path.join(config.repoPath, "package.json"), "utf-8");
  });

  it("discovers defaults in the execution repo rather than the process cwd", async () => {
    expect(config.repoPath).not.toBe(process.cwd());
    vi.mocked(readFile).mockImplementation(async (file) => {
      if (file !== path.join(config.repoPath, "package.json")) {
        throw new Error(`Unexpected package path: ${file}`);
      }
      return JSON.stringify({ scripts: { test: "vitest" } });
    });
    runCommand.mockResolvedValue(ok("pnpm"));

    await repoTestHandler({});

    expect(commandsSent()).toEqual([
      ["pnpm", ["install", "--frozen-lockfile"]],
      ["pnpm", ["test"]],
    ]);
    expect(runCommand).toHaveBeenCalledWith("pnpm", ["test"], {
      cwd: undefined,
      timeout: 300_000,
    });
  });

  it("omits build when the target package has no build script", async () => {
    vi.mocked(readFile).mockResolvedValue(JSON.stringify({ scripts: { lint: "eslint .", test: "vitest" } }));
    runCommand.mockResolvedValue(ok("pnpm"));

    await repoTestHandler({ worktreePath: "/repo/without-build" });

    expect(readFile).toHaveBeenCalledWith("/repo/without-build/package.json", "utf-8");
    expect(commandsSent()).toEqual([
      ["pnpm", ["install", "--frozen-lockfile"]],
      ["pnpm", ["lint"]],
      ["pnpm", ["test"]],
    ]);
  });

  it.each([{}, { scripts: {} }])("keeps install when no scripts exist: %j", async (pkg) => {
    vi.mocked(readFile).mockResolvedValue(JSON.stringify(pkg));
    runCommand.mockResolvedValue(ok("pnpm"));

    await repoTestHandler({});

    expect(commandsSent()).toEqual([["pnpm", ["install", "--frozen-lockfile"]]]);
  });

  it("rejects unreadable or invalid package metadata before running defaults", async () => {
    vi.mocked(readFile).mockRejectedValueOnce(new Error("ENOENT"));
    await expect(repoTestHandler({})).rejects.toThrow("ENOENT");
    vi.mocked(readFile).mockResolvedValueOnce("not JSON");
    await expect(repoTestHandler({})).rejects.toThrow();
    expect(runCommand).not.toHaveBeenCalled();
  });

  it("stops at the first failing command and reports it", async () => {
    runCommand
      .mockResolvedValueOnce(ok("pnpm install --frozen-lockfile"))
      .mockResolvedValueOnce(fail("pnpm lint", "eslint: 3 errors"));

    const result = await repoTestHandler({
      commands: ["pnpm install --frozen-lockfile", "pnpm lint", "pnpm test"],
    });

    expect(runCommand).toHaveBeenCalledTimes(2);
    expect(result.passed).toBe(false);
    expect(result.exitCode).toBe(1);
    expect(result.failedTests).toEqual(["pnpm lint"]);
  });

  it("surfaces the failing command's stderr detail instead of 'Unknown error'", async () => {
    runCommand.mockResolvedValue(fail("pnpm test", "FAIL src/x.test.ts — expected 2 to be 3"));

    const result = await repoTestHandler({ commands: ["pnpm test"] });

    expect(result.results[0].stderr).toContain("expected 2 to be 3");
    expect(result.failedTests).toEqual(["pnpm test"]);
  });

  it("records a thrown spawn failure as a failed result and stops", async () => {
    runCommand.mockRejectedValue(new Error("spawn ENOENT"));

    const result = await repoTestHandler({ commands: ["pnpm test", "pnpm build"] });

    expect(runCommand).toHaveBeenCalledTimes(1);
    expect(result.passed).toBe(false);
    expect(result.results[0]).toMatchObject({
      command: "pnpm test",
      stderr: "spawn ENOENT",
      exitCode: 1,
    });
  });

  it("passes worktreePath as cwd and the timeout to runCommand", async () => {
    runCommand.mockResolvedValue(ok("pnpm"));

    await repoTestHandler({
      commands: ["pnpm test"],
      worktreePath: "/tmp/wt",
      timeoutSeconds: 42,
    });

    expect(runCommand).toHaveBeenCalledWith("pnpm", ["test"], {
      cwd: "/tmp/wt",
      timeout: 42_000,
    });
  });

  it("defaults the timeout to 300 seconds", async () => {
    runCommand.mockResolvedValue(ok("pnpm"));

    await repoTestHandler({ commands: ["pnpm test"] });

    expect(runCommand).toHaveBeenCalledWith("pnpm", ["test"], {
      cwd: undefined,
      timeout: 300_000,
    });
  });
});

describe("repo_test — schema boundary", () => {
  it("still rejects a non-numeric timeoutSeconds", () => {
    expect(() => RepoTestInputSchema.parse({ timeoutSeconds: "soon" })).toThrow();
  });

  it("still rejects a non-array commands field", () => {
    expect(() => RepoTestInputSchema.parse({ commands: "pnpm test" })).toThrow();
  });

  // #1025 regression class, consolidation resolution: the wire schema is
  // omission-only, so clients must omit optional fields instead of sending
  // explicit nulls — and the runtime schema enforces that.
  it("rejects explicit null for optional fields instead of silently accepting it", () => {
    expect(() => RepoTestInputSchema.parse({ commands: null })).toThrow();
    expect(() => RepoTestInputSchema.parse({ worktreePath: null })).toThrow();
  });
});
