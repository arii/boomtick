import { describe, it, expect, vi, beforeEach } from "vitest";
import { getPrReviewsHandler } from "./github.get_pr_reviews.js";
import { getPrCommitsHandler } from "./github.get_pr_commits.js";
import { getWorkflowRunsHandler } from "./repo.get_workflow_runs.js";
import * as shell from "../lib/shell.js";

vi.mock("../lib/shell.js", () => ({
  runCommand: vi.fn(),
}));

describe("MCP GitHub tools", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("getPrReviewsHandler", () => {
    it("should fetch PR reviews via td gh read-pr-reviews", async () => {
      vi.mocked(shell.runCommand).mockResolvedValueOnce({
        stdout: JSON.stringify({
          status: "success",
          reviews: [{ id: 1, state: "APPROVED", body: "LGTM" }],
          review_count: 1,
        }),
        stderr: "",
        exitCode: 0,
        durationMs: 10,
        command: "td gh read-pr-reviews",
      });

      const res = await getPrReviewsHandler({ prNumber: 819, repo: "arii/boomtick" });

      expect(shell.runCommand).toHaveBeenCalledWith("td", [
        "gh",
        "read-pr-reviews",
        "--pr-number",
        "819",
        "--repo",
        "arii/boomtick",
      ]);
      expect(res).toEqual({
        reviews: [{ id: 1, state: "APPROVED", body: "LGTM" }],
        reviewCount: 1,
      });
    });
  });

  describe("getPrCommitsHandler", () => {
    it("should list PR commits via td gh list-pr-commits", async () => {
      vi.mocked(shell.runCommand).mockResolvedValueOnce({
        stdout: JSON.stringify({
          status: "success",
          commits: [{ sha: "abc1234", author: "Dev", message: "feat: test" }],
        }),
        stderr: "",
        exitCode: 0,
        durationMs: 10,
        command: "td gh list-pr-commits",
      });

      const res = await getPrCommitsHandler({ prNumber: 819, repo: "arii/boomtick" });

      expect(shell.runCommand).toHaveBeenCalledWith("td", [
        "gh",
        "list-pr-commits",
        "--pr-number",
        "819",
        "--repo",
        "arii/boomtick",
      ]);
      expect(res).toEqual({
        commits: [{ sha: "abc1234", author: "Dev", message: "feat: test" }],
      });
    });
  });

  describe("getWorkflowRunsHandler", () => {
    it("should fetch workflow runs via td repo workflow-runs", async () => {
      vi.mocked(shell.runCommand).mockResolvedValueOnce({
        stdout: JSON.stringify({
          status: "success",
          workflow_runs: [{ id: 10, name: "CI" }],
        }),
        stderr: "",
        exitCode: 0,
        durationMs: 10,
        command: "td repo workflow-runs",
      });

      const res = await getWorkflowRunsHandler({
        branch: "main",
        event: "push",
        repo: "arii/boomtick",
      });

      expect(shell.runCommand).toHaveBeenCalledWith("td", [
        "repo",
        "workflow-runs",
        "--repo",
        "arii/boomtick",
        "--branch",
        "main",
        "--event",
        "push",
      ]);
      expect(res).toEqual({
        workflowRuns: [{ id: 10, name: "CI" }],
      });
    });

    it("should surface 404 Not Found error with clear repository message", async () => {
      vi.mocked(shell.runCommand).mockResolvedValueOnce({
        stdout: JSON.stringify({
          status: "error",
          message: "GitHub API Error: Not Found",
          code: 404,
        }),
        stderr: "",
        exitCode: 1,
        durationMs: 10,
        command: "td repo workflow-runs",
      });

      await expect(
        getWorkflowRunsHandler({
          repo: "arii/remote-server",
        })
      ).rejects.toThrow("Repository 'arii/remote-server' not found (404)");
    });

    it("should surface API error message from json payload", async () => {
      vi.mocked(shell.runCommand).mockResolvedValueOnce({
        stdout: JSON.stringify({
          status: "error",
          message: "Bad credentials",
          code: 401,
        }),
        stderr: "",
        exitCode: 1,
        durationMs: 10,
        command: "td repo workflow-runs",
      });

      await expect(
        getWorkflowRunsHandler({
          repo: "arii/boomtick",
        })
      ).rejects.toThrow("Failed to fetch workflow runs: Bad credentials");
    });

    it("should fallback to stderr when stdout is not JSON", async () => {
      vi.mocked(shell.runCommand).mockResolvedValueOnce({
        stdout: "",
        stderr: "network timeout",
        exitCode: 1,
        durationMs: 10,
        command: "td repo workflow-runs",
      });

      await expect(
        getWorkflowRunsHandler({
          repo: "arii/boomtick",
        })
      ).rejects.toThrow("Failed to fetch workflow runs: network timeout");
    });
  });
});
