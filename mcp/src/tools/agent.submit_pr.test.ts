import { describe, it, expect, vi, beforeEach } from "vitest";
import { agentSubmitPrHandler } from "./agent.submit_pr.js";
import * as shellModule from "../lib/shell.js";

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
    });

    expect(runSpy).toHaveBeenNthCalledWith(
      1,
      "git",
      ["push", "origin", "feat/x"],
      { cwd: undefined }
    );
    expect(runSpy).toHaveBeenNthCalledWith(
      2,
      "gh",
      ["pr", "create", "--base", "main", "--head", "feat/x", "--title", "T", "--body", "B", "--draft"],
      { cwd: undefined }
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
    });

    expect(runSpy).toHaveBeenNthCalledWith(
      2,
      "gh",
      ["pr", "create", "--base", "dev", "--head", "feat/x", "--title", "T", "--body", "", "--repo", "o/r"],
      { cwd: undefined }
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
      agentSubmitPrHandler({ branch: "feat/x", title: "T", pushMode: true })
    ).rejects.toThrow("Failed to push branch feat/x");
    expect(runSpy).toHaveBeenCalledTimes(1);
  });

  it("surfaces gh failures", async () => {
    vi.spyOn(shellModule, "runCommand")
      .mockResolvedValueOnce({ exitCode: 0, stdout: "", stderr: "" } as any)
      .mockResolvedValueOnce({ exitCode: 1, stdout: "", stderr: "boom" } as any);

    await expect(
      agentSubmitPrHandler({ branch: "feat/x", title: "T", pushMode: true })
    ).rejects.toThrow("Failed to open PR");
  });
});
