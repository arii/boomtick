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
      eligible_count: 1,
      merged_count: null,
      results: [
        {
          pr_number: 12,
          title: "PR 12",
          draft: false,
          review_decision: "APPROVED",
          has_failing_checks: false,
          mergeable: "MERGEABLE",
          is_eligible: true,
          reason: null,
        },
      ],
    } as any);

    const res = await agentMergeApprovedHandler({ repo: "test/repo" });
    expect(runTDCliSpy).toHaveBeenCalledWith(
      ["agent", "merge-approved", "-r", "test/repo", "--dry-run"],
      "agent merge-approved"
    );
    expect(res.eligible_count).toBe(1);
    expect(res.mode).toBe("dry-run");
  });

  it("calls td agent merge-approved with --execute when execute is true", async () => {
    const runTDCliSpy = vi.spyOn(cliModule, "runTDCli").mockResolvedValue({
      status: "success",
      mode: "execute",
      total_evaluated: 1,
      eligible_count: 1,
      merged_count: 1,
      results: [
        {
          pr_number: 12,
          title: "PR 12",
          draft: false,
          review_decision: "APPROVED",
          has_failing_checks: false,
          mergeable: "MERGEABLE",
          is_eligible: true,
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
    expect(res.merged_count).toBe(1);
    expect(res.mode).toBe("execute");
  });
});
