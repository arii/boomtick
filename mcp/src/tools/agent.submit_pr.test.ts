import { describe, it, expect, vi, beforeEach } from "vitest";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { agentSubmitPrHandler } from "./agent.submit_pr.js";
import * as shellModule from "../lib/shell.js";
import type { ShellResult } from "../lib/shell.js";

function mkWorktree(tools: string[] = ["td.init_and_rag", "td.verify_scope"]): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "submit-pr-"));
  fs.writeFileSync(
    path.join(dir, ".agent_tool_receipt.json"),
    JSON.stringify(tools.map((tool) => ({ tool, timestamp: "2026-01-01T00:00:00.000Z" }))),
    "utf8",
  );
  return dir;
}

function tdResponse(over: Record<string, unknown> = {}): ShellResult {
  return {
    exitCode: 0,
    stdout: JSON.stringify({
      status: "success",
      url: "https://github.com/o/r/pull/1",
      branch: "feat/x",
      base: "main",
      draft: true,
      ...over,
    }),
    stderr: "",
    durationMs: 0,
    command: "td",
  };
}

describe("agent_submit_pr MCP tool handler", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("delegates push and PR open to td agent submit-pr (issue 1139)", async () => {
    const dir = mkWorktree();
    const runSpy = vi
      .spyOn(shellModule, "runCommand")
      .mockResolvedValueOnce(tdResponse());

    const res = await agentSubmitPrHandler({
      branch: "feat/x",
      title: "T",
      body: "B",
      pushMode: true,
      worktreePath: dir,
    });

    expect(runSpy).toHaveBeenCalledTimes(1);
    expect(runSpy).toHaveBeenCalledWith("td", [
      "agent",
      "submit-pr",
      "--worktree",
      dir,
      "--title",
      "T",
      "--body",
      "B",
      "--base",
      "main",
      "--json",
    ]);
    expect(res).toEqual({
      status: "success",
      url: "https://github.com/o/r/pull/1",
      branch: "feat/x",
      baseBranch: "main",
      draft: true,
    });
  });

  it("honours base branch, repo and non-draft", async () => {
    const runSpy = vi
      .spyOn(shellModule, "runCommand")
      .mockResolvedValueOnce(tdResponse({ base: "dev", draft: false }));

    await agentSubmitPrHandler({
      repo: "o/r",
      branch: "feat/x",
      baseBranch: "dev",
      title: "T",
      draft: false,
      pushMode: true,
      worktreePath: mkWorktree(["repo.read_agent_context", "td.audit_worktree"]),
    });

    expect(runSpy).toHaveBeenCalledWith("td", [
      "agent",
      "submit-pr",
      "--worktree",
      expect.any(String),
      "--title",
      "T",
      "--body",
      "",
      "--base",
      "dev",
      "--repo",
      "o/r",
      "--no-draft",
      "--json",
    ]);
  });

  it("accepts td.init / td.rag receipts as RAG proof", async () => {
    const runSpy = vi
      .spyOn(shellModule, "runCommand")
      .mockResolvedValueOnce(tdResponse());

    await agentSubmitPrHandler({
      branch: "feat/x",
      title: "T",
      pushMode: true,
      worktreePath: mkWorktree(["td.init", "td.verify_scope"]),
    });
    expect(runSpy).toHaveBeenCalledTimes(1);
  });

  it("refuses without pushMode", async () => {
    await expect(
      agentSubmitPrHandler({ branch: "feat/x", title: "T" })
    ).rejects.toThrow("pushMode must be true");
  });

  it("refuses when the worktree branch differs from the request", async () => {
    vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce(
      tdResponse({ branch: "feat/other" })
    );

    await expect(
      agentSubmitPrHandler({ branch: "feat/x", title: "T", pushMode: true, worktreePath: mkWorktree() })
    ).rejects.toThrow("Refusing to submit");
  });

  it("surfaces td CLI failures without opening a PR", async () => {
    const runSpy = vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce({
      exitCode: 1,
      stdout: "",
      stderr: "denied",
      durationMs: 0,
      command: "td",
    });

    await expect(
      agentSubmitPrHandler({ branch: "feat/x", title: "T", pushMode: true, worktreePath: mkWorktree() })
    ).rejects.toThrow("Failed to submit PR via td agent submit-pr");
    expect(runSpy).toHaveBeenCalledTimes(1);
  });

  it("blocks submission without tool receipts (issue 1146)", async () => {
    const runSpy = vi.spyOn(shellModule, "runCommand");
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "submit-pr-"));
    await expect(
      agentSubmitPrHandler({ branch: "feat/x", title: "T", pushMode: true, worktreePath: dir })
    ).rejects.toThrow("missing mandatory tool receipts");
    expect(runSpy).not.toHaveBeenCalled();
  });

  it("blocks submission with RAG receipts but no scope receipts (issue 1146)", async () => {
    const runSpy = vi.spyOn(shellModule, "runCommand");
    await expect(
      agentSubmitPrHandler({
        branch: "feat/x",
        title: "T",
        pushMode: true,
        worktreePath: mkWorktree(["td.init_and_rag"]),
      })
    ).rejects.toThrow("usedScope=false");
    expect(runSpy).not.toHaveBeenCalled();
  });
});
