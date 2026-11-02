import { describe, it, expect, vi, beforeEach } from "vitest";
import { agentMergeApprovedHandler } from "./agent.merge_approved.js";
import * as cliModule from "./jules/cli.js";

describe("agent_merge_approved MCP tool handler", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("calls td agent merge-approved with dry-run by default", async () => {
    const runTDCliSpy = vi.spyOn(cliModule, "runTDCli").mockResolvedValue({
      status: "success",
      mode: "dry-run",
      total_evaluated: 1,
      eligibleCount: 1,
      mergedCount: null,
      results: [
        {
          prNumber: 12,
          title: "PR 12",
          draft: false,
          reviewDecision: "APPROVED",
          hasFailingChecks: false,
          mergeable: "MERGEABLE",
          isEligible: true,
          reason: null,
        },
      ],
    } as any);

    const res = await agentMergeApprovedHandler({ repo: "test/repo" });
    expect(runTDCliSpy).toHaveBeenCalledWith(
      ["agent", "merge-approved", "-r", "test/repo", "--dry-run"],
      "agent merge-approved"
    );
    expect(res.eligibleCount).toBe(1);
    expect(res.mode).toBe("dry-run");
  });

  it("calls td agent merge-approved with --execute when execute is true", async () => {
    const runTDCliSpy = vi.spyOn(cliModule, "runTDCli").mockResolvedValue({
      status: "success",
      mode: "execute",
      totalEvaluated: 1,
      eligibleCount: 1,
      mergedCount: 1,
      results: [
        {
          prNumber: 12,
          title: "PR 12",
          draft: false,
          reviewDecision: "APPROVED",
          hasFailingChecks: false,
          mergeable: "MERGEABLE",
          isEligible: true,
          reason: null,
          merged: true,
          message: "Merged successfully",
        },
      ],
    } as any);

    const res = await agentMergeApprovedHandler({ repo: "test/repo", execute: true });
    expect(runTDCliSpy).toHaveBeenCalledWith(
      ["agent", "merge-approved", "-r", "test/repo", "--execute"],
      "agent merge-approved"
    );
    expect(res.mergedCount).toBe(1);
    expect(res.mode).toBe("execute");
  });
});
