import { describe, it, expect, vi, beforeEach, expectTypeOf } from "vitest";
import { runTDCli } from "./tdCli.js";
import type { TDCliResponse, TDMultiRepoEntry } from "./tdCli.js";
import * as shellModule from "./shell.js";
import type { ShellResult } from "./shell.js";
import * as sessionManager from "./session_manager.js";
import { readAgentContextHandler } from "../tools/repo.read_agent_context.js";

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
    const res = await readAgentContextHandler({ all: true });
    if (!("ecosystem" in res)) throw new Error("expected ecosystem response");
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
