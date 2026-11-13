import { beforeEach, describe, expect, it, vi } from "vitest";
import { runTestsHandler, RunTestsInputSchema } from "./repo.run_tests.js";
import * as shell from "../lib/shell.js";

vi.mock("../lib/shell.js", () => ({ runCommand: vi.fn() }));

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

describe("repo.run_tests — regex tokenizer", () => {
  it("splits plain space-separated commands", async () => {
    runCommand.mockResolvedValue(ok("pnpm lint"));

    await runTestsHandler({ commands: ["pnpm lint --fix"] });

    expect(commandsSent()).toEqual([["pnpm", ["lint", "--fix"]]]);
  });

  it("keeps double-quoted arguments together and unescapes \\\"", async () => {
    runCommand.mockResolvedValue(ok("node"));

    await runTestsHandler({
      commands: ['node -e "console.log(\\"hello world\\")"'],
    });

    expect(commandsSent()).toEqual([
      ["node", ["-e", 'console.log("hello world")']],
    ]);
  });

  it("keeps single-quoted arguments together", async () => {
    runCommand.mockResolvedValue(ok("grep"));

    await runTestsHandler({ commands: ["grep 'a b c' file.txt"] });

    expect(commandsSent()).toEqual([["grep", ["a b c", "file.txt"]]]);
  });

  it("keeps escaped single quotes inside single-quoted arguments", async () => {
    runCommand.mockResolvedValue(ok("grep"));

    await runTestsHandler({ commands: ["grep 'it\\'s' file.txt"] });

    expect(commandsSent()).toEqual([["grep", ["it's", "file.txt"]]]);
  });

  it("collapses runs of whitespace", async () => {
    runCommand.mockResolvedValue(ok("pnpm"));

    await runTestsHandler({ commands: ["pnpm   test    --run"] });

    expect(commandsSent()).toEqual([["pnpm", ["test", "--run"]]]);
  });
});

describe("repo.run_tests — execution semantics", () => {
  it("runs the default four commands when none are given", async () => {
    runCommand.mockResolvedValue(ok("pnpm"));

    const result = await runTestsHandler({});

    expect(runCommand).toHaveBeenCalledTimes(4);
    expect(commandsSent()[0]).toEqual(["pnpm", ["install", "--frozen-lockfile"]]);
    expect(commandsSent()[3]).toEqual(["pnpm", ["build"]]);
    expect(result.passed).toBe(true);
    expect(result.failedTests).toEqual([]);
  });

  it("stops at the first failing command and reports it", async () => {
    runCommand
      .mockResolvedValueOnce(ok("pnpm install --frozen-lockfile"))
      .mockResolvedValueOnce(fail("pnpm lint", "eslint: 3 errors"));

    const result = await runTestsHandler({ commands: ["pnpm install --frozen-lockfile", "pnpm lint", "pnpm test"] });

    expect(runCommand).toHaveBeenCalledTimes(2);
    expect(result.passed).toBe(false);
    expect(result.exitCode).toBe(1);
    expect(result.failedTests).toEqual(["pnpm lint"]);
  });

  it("surfaces the failing command's stderr detail instead of 'Unknown error'", async () => {
    runCommand.mockResolvedValue(fail("pnpm test", "FAIL src/x.test.ts — expected 2 to be 3"));

    const result = await runTestsHandler({ commands: ["pnpm test"] });

    expect(result.results[0].stderr).toContain("expected 2 to be 3");
    expect(result.failedTests).toEqual(["pnpm test"]);
  });

  it("records a thrown spawn failure as a failed result and stops", async () => {
    runCommand.mockRejectedValue(new Error("spawn ENOENT"));

    const result = await runTestsHandler({ commands: ["pnpm test", "pnpm build"] });

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

    await runTestsHandler({
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

    await runTestsHandler({ commands: ["pnpm test"] });

    expect(runCommand).toHaveBeenCalledWith("pnpm", ["test"], {
      cwd: undefined,
      timeout: 300_000,
    });
  });
});

describe("repo.run_tests — #1025 regression: explicit null args", () => {
  it("accepts null for every optional field and uses the defaults", async () => {
    runCommand.mockResolvedValue(ok("pnpm"));

    const result = await runTestsHandler({
      commands: null,
      timeoutSeconds: null,
      worktreePath: null,
    });

    // null commands fall back to the default pipeline; null timeout to 300s.
    expect(runCommand).toHaveBeenCalledTimes(4);
    expect(runCommand).toHaveBeenCalledWith("pnpm", ["test"], {
      cwd: undefined,
      timeout: 300_000,
    });
    expect(result.passed).toBe(true);
  });
});

describe("repo.run_tests — schema boundary", () => {
  it("still rejects a non-numeric timeoutSeconds", () => {
    expect(() => RunTestsInputSchema.parse({ timeoutSeconds: "soon" })).toThrow();
  });

  it("still rejects a non-array commands field", () => {
    expect(() => RunTestsInputSchema.parse({ commands: "pnpm test" })).toThrow();
  });
});
