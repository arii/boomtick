import { describe, it, expect, vi, beforeEach, expectTypeOf } from "vitest";
import { runTDCli } from "./tdCli.js";
import type { TDCliResponse, TDMultiRepoEntry } from "./tdCli.js";
import * as shellModule from "./shell.js";
import type { ShellResult } from "./shell.js";
import * as sessionManager from "./session_manager.js";
import { repoContextHandler } from "../tools/repo.context.js";

function shellOk(stdout: string): ShellResult {
  return { exitCode: 0, stdout, stderr: "", durationMs: 0, command: "td" };
}

// Regression tests for issue #1222 item (1): the td CLI boundary.
// runTDCli is the single funnel every tool reads unvalidated JSON through,
// so malformed output must throw loudly here instead of flowing downstream
// as undefined fields.
describe("runTDCli type boundary (issue 1222)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("rejects a td error status with the action message", async () => {
    vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce(
      shellOk(JSON.stringify({ status: "error", message: "boom" })),
    );
    await expect(runTDCli(["gh", "view"], "view PR")).rejects.toThrow(
      "Failed to view PR: boom",
    );
  });

  it("rejects non-JSON stdout on exit 0 instead of flowing as undefined", async () => {
    vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce(
      shellOk("this is not json"),
    );
    await expect(runTDCli(["repo", "ci-logs"])).rejects.toThrow(
      "non-JSON output",
    );
  });

  it("rejects a nonzero exit with stderr context", async () => {
    vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce({
      exitCode: 1,
      stdout: "",
      stderr: "denied",
      durationMs: 0,
      command: "td",
    });
    await expect(runTDCli(["agent", "submit-pr"], "submit")).rejects.toThrow(
      "Failed to submit: denied",
    );
  });

  it("returns parsed success output with missing fields as undefined", async () => {
    vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce(
      shellOk(JSON.stringify({ status: "success" })),
    );
    const out = await runTDCli(["multi-repo", "status"]);
    expect(out.status).toBe("success");
    expect(out.repos).toBeUndefined();
    expect(out.total).toBeUndefined();
  });

  it("defaults missing repos/total to [] and 0 at the ecosystem consumer", async () => {
    vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce(
      shellOk(JSON.stringify({ status: "success" })),
    );
    vi.spyOn(sessionManager, "recordToolReceipt").mockImplementation(() => {});
    const res = await repoContextHandler({ scope: "all" });
    if (!("ecosystem" in res) || !res.ecosystem) throw new Error("expected ecosystem response");
    expect(res.repos).toEqual([]);
    expect(res.total).toBe(0);
  });

  it("types the known fields so rows are TDMultiRepoEntry, extras stay unknown", () => {
    // Red on pre-fix code where the index signature was `any`.
    expectTypeOf<TDCliResponse["repos"]>().toEqualTypeOf<
      TDMultiRepoEntry[] | undefined
    >();
    expectTypeOf<TDCliResponse["total"]>().toEqualTypeOf<number | undefined>();
    expectTypeOf<TDCliResponse[string]>().toEqualTypeOf<unknown>();
  });
});

// Regression tests for audit H1: td may print warn/log lines before the
// JSON payload, and long-running subcommands were killed by the generic
// 60s shell default.
describe("runTDCli reliability (audit H1)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("parses a JSON payload that follows non-JSON warn lines", async () => {
    vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce(
      shellOk('warning: stale index detected\n{"status": "success", "repos": []}'),
    );
    const out = await runTDCli(["multi-repo", "status"]);
    expect(out.status).toBe("success");
    expect(out.repos).toEqual([]);
  });

  it("still rejects stdout with no JSON payload at all", async () => {
    vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce(
      shellOk("warning: nothing useful here"),
    );
    await expect(runTDCli(["repo", "ci-logs"])).rejects.toThrow("non-JSON output");
  });

  it("surfaces an error status that follows a warn prefix", async () => {
    vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce(
      shellOk('warn: degraded\n{"status": "error", "message": "index locked"}'),
    );
    await expect(runTDCli(["repo", "workflow-runs"], "fetch workflow runs")).rejects.toThrow(
      "Failed to fetch workflow runs: index locked",
    );
  });

  it("passes a 60s default timeout for ordinary subcommands", async () => {
    const spy = vi
      .spyOn(shellModule, "runCommand")
      .mockResolvedValueOnce(shellOk('{"status": "success"}'));
    await runTDCli(["multi-repo", "status"]);
    expect(spy).toHaveBeenCalledWith("td", ["multi-repo", "status"], { timeout: 60_000 });
  });

  it("passes a generous default timeout for index-building subcommands", async () => {
    const spy = vi
      .spyOn(shellModule, "runCommand")
      .mockResolvedValue(shellOk('{"status": "success"}'));
    await runTDCli(["init", "--json"]);
    await runTDCli(["audit-code", "--worktree", "/tmp/wt", "--json"]);
    await runTDCli(["rag", "query", "--query", "q", "--json"]);
    expect(spy).toHaveBeenNthCalledWith(1, "td", ["init", "--json"], { timeout: 600_000 });
    expect(spy).toHaveBeenNthCalledWith(2, "td", ["audit-code", "--worktree", "/tmp/wt", "--json"], {
      timeout: 600_000,
    });
    expect(spy).toHaveBeenNthCalledWith(3, "td", ["rag", "query", "--query", "q", "--json"], {
      timeout: 600_000,
    });
  });

  it("lets the caller override the timeout explicitly", async () => {
    const spy = vi
      .spyOn(shellModule, "runCommand")
      .mockResolvedValueOnce(shellOk('{"status": "success"}'));
    await runTDCli(["init", "--json"], "initialize repo", { timeoutMs: 1234 });
    expect(spy).toHaveBeenCalledWith("td", ["init", "--json"], { timeout: 1234 });
  });
});
