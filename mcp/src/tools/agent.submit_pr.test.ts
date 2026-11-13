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
    ], { timeout: 60_000 });
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
    ], { timeout: 60_000 });
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

  it("skips telemetry without an explicit worktreePath (issue 1157)", async () => {
    const cwdFile = path.join(process.cwd(), ".agent_tool_telemetry.jsonl");
    if (fs.existsSync(cwdFile)) {
      fs.rmSync(cwdFile);
    }
    await expect(
      agentSubmitPrHandler({ branch: "feat/x", title: "T" })
    ).rejects.toThrow("pushMode must be true");
    expect(fs.existsSync(cwdFile)).toBe(false);
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

  it("names the unreadable receipt file instead of reporting missing receipts", async () => {
    const runSpy = vi.spyOn(shellModule, "runCommand");
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "submit-pr-"));
    fs.writeFileSync(path.join(dir, ".agent_tool_receipt.json"), "{corrupt", "utf8");

    await expect(
      agentSubmitPrHandler({ branch: "feat/x", title: "T", pushMode: true, worktreePath: dir })
    ).rejects.toThrow("tool receipt file is unreadable");
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

  it("emits telemetry lines on success and on block (issue 1157)", async () => {
    vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce(tdResponse());
    const okDir = mkWorktree();
    await agentSubmitPrHandler({
      branch: "feat/x",
      title: "T",
      pushMode: true,
      worktreePath: okDir,
    });
    const okLines = fs
      .readFileSync(path.join(okDir, ".agent_tool_telemetry.jsonl"), "utf8")
      .split("\n")
      .filter((l) => l.trim().length > 0)
      .map((l) => JSON.parse(l));
    expect(okLines).toHaveLength(1);
    expect(okLines[0].tool).toBe("agent.submit_pr");
    expect(okLines[0].session).toBe(okDir);
    expect(okLines[0].ok).toBe(true);
    expect(okLines[0].ms).toBeGreaterThanOrEqual(0);

    const blockedDir = fs.mkdtempSync(path.join(os.tmpdir(), "submit-pr-"));
    await expect(
      agentSubmitPrHandler({ branch: "feat/x", title: "T", pushMode: true, worktreePath: blockedDir })
    ).rejects.toThrow("missing mandatory tool receipts");
    const blockedLines = fs
      .readFileSync(path.join(blockedDir, ".agent_tool_telemetry.jsonl"), "utf8")
      .split("\n")
      .filter((l) => l.trim().length > 0)
      .map((l) => JSON.parse(l));
    expect(blockedLines).toHaveLength(1);
    expect(blockedLines[0].ok).toBe(false);
    expect(blockedLines[0].detail).toMatch("missing mandatory tool receipts");
  });
});
