import { describe, it, expect, vi, beforeEach } from "vitest";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { agentSubmitPrHandler } from "./agent.submit_pr.js";
import * as shellModule from "../lib/shell.js";

function mkWorktree(tools: string[] = ["td.init_and_rag", "td.verify_scope"]): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "submit-pr-"));
  fs.writeFileSync(
    path.join(dir, ".agent_tool_receipt.json"),
    JSON.stringify(tools.map((tool) => ({ tool, timestamp: "2026-01-01T00:00:00.000Z" }))),
    "utf8",
  );
  return dir;
}

describe("agent_submit_pr MCP tool handler", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("pushes the branch and opens a draft PR", async () => {
    const runSpy = vi
      .spyOn(shellModule, "runCommand")
      .mockResolvedValueOnce({ exitCode: 0, stdout: "", stderr: "" } as any)
      .mockResolvedValueOnce({
        exitCode: 0,
        stdout: "https://github.com/o/r/pull/1\n",
        stderr: "",
      } as any);

    const res = await agentSubmitPrHandler({
      branch: "feat/x",
      title: "T",
      body: "B",
      pushMode: true,
      worktreePath: mkWorktree(),
    });

    expect(runSpy).toHaveBeenNthCalledWith(
      1,
      "git",
      ["push", "origin", "feat/x"],
      { cwd: expect.any(String) }
    );
    expect(runSpy).toHaveBeenNthCalledWith(
      2,
      "gh",
      ["pr", "create", "--base", "main", "--head", "feat/x", "--title", "T", "--body", "B", "--draft"],
      { cwd: expect.any(String) }
    );
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
      .mockResolvedValueOnce({ exitCode: 0, stdout: "", stderr: "" } as any)
      .mockResolvedValueOnce({ exitCode: 0, stdout: "url", stderr: "" } as any);

    await agentSubmitPrHandler({
      repo: "o/r",
      branch: "feat/x",
      baseBranch: "dev",
      title: "T",
      draft: false,
      pushMode: true,
      worktreePath: mkWorktree(["repo.read_agent_context", "td.audit_worktree"]),
    });

    expect(runSpy).toHaveBeenNthCalledWith(
      2,
      "gh",
      ["pr", "create", "--base", "dev", "--head", "feat/x", "--title", "T", "--body", "", "--repo", "o/r"],
      { cwd: expect.any(String) }
    );
  });

  it("refuses without pushMode", async () => {
    await expect(
      agentSubmitPrHandler({ branch: "feat/x", title: "T" })
    ).rejects.toThrow("pushMode must be true");
  });

  it("surfaces push failures without opening a PR", async () => {
    const runSpy = vi
      .spyOn(shellModule, "runCommand")
      .mockResolvedValueOnce({ exitCode: 1, stdout: "", stderr: "denied" } as any);

    await expect(
      agentSubmitPrHandler({ branch: "feat/x", title: "T", pushMode: true, worktreePath: mkWorktree() })
    ).rejects.toThrow("Failed to push branch feat/x");
    expect(runSpy).toHaveBeenCalledTimes(1);
  });

  it("surfaces gh failures", async () => {
    vi.spyOn(shellModule, "runCommand")
      .mockResolvedValueOnce({ exitCode: 0, stdout: "", stderr: "" } as any)
      .mockResolvedValueOnce({ exitCode: 1, stdout: "", stderr: "boom" } as any);

    await expect(
      agentSubmitPrHandler({ branch: "feat/x", title: "T", pushMode: true, worktreePath: mkWorktree() })
    ).rejects.toThrow("Failed to open PR");
  });

  it("blocks submission without tool receipts (#1146)", async () => {
    const runSpy = vi.spyOn(shellModule, "runCommand");
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "submit-pr-"));
    await expect(
      agentSubmitPrHandler({ branch: "feat/x", title: "T", pushMode: true, worktreePath: dir })
    ).rejects.toThrow("missing mandatory tool receipts");
    expect(runSpy).not.toHaveBeenCalled();
  });

  it("blocks submission with RAG receipts but no scope receipts (#1146)", async () => {
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
