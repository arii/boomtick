import { beforeEach, describe, expect, it, vi } from "vitest";
import { readCiLogsHandler } from "./repo.read_ci_logs.js";
import * as tdCli from "../lib/tdCli.js";

vi.mock("../lib/tdCli.js", () => ({ runTDCli: vi.fn() }));

const runTDCli = vi.mocked(tdCli.runTDCli);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("repo.read_ci_logs — PR log mode", () => {
  it("fetches CI logs for a PR", async () => {
    runTDCli.mockResolvedValue({ checks: ["ok"], failedChecks: [], logs: "build log" });

    const result = await readCiLogsHandler({ prNumber: 9 });

    expect(runTDCli).toHaveBeenCalledWith(["repo", "ci-logs", "9"]);
    expect(result).toEqual({ checks: ["ok"], failedChecks: [], logs: "build log" });
  });

  it("passes --all and the repo override", async () => {
    runTDCli.mockResolvedValue({ checks: [], failedChecks: [], logs: "" });

    await readCiLogsHandler({ prNumber: 9, all: true, repo: "org/other" });

    expect(runTDCli).toHaveBeenCalledWith([
      "repo", "ci-logs", "9", "--all", "--repo", "org/other",
    ]);
  });

  it("appends workflow runs when includeRuns is set", async () => {
    runTDCli
      .mockResolvedValueOnce({ checks: [], failedChecks: [], logs: "" })
      .mockResolvedValueOnce({ workflow_runs: [{ id: 1 }] });

    const result = await readCiLogsHandler({ prNumber: 9, includeRuns: true });

    expect(runTDCli).toHaveBeenNthCalledWith(2, ["repo", "workflow-runs"], "fetch workflow runs");
    expect(result.workflowRuns).toEqual([{ id: 1 }]);
  });

  it("propagates td failure detail instead of 'Unknown error'", async () => {
    runTDCli.mockRejectedValue(
      new Error("td command failed (repo ci-logs 9): gh: Not Found (HTTP 404)")
    );

    await expect(readCiLogsHandler({ prNumber: 9 })).rejects.toThrow(/Not Found \(HTTP 404\)/);
    await expect(readCiLogsHandler({ prNumber: 9 })).rejects.not.toThrow(/^Unknown error$/);
  });
});

describe("repo.read_ci_logs — workflow-runs mode (no prNumber)", () => {
  it("lists workflow runs with branch, event and repo filters", async () => {
    runTDCli.mockResolvedValue({ workflow_runs: [{ id: 2 }] });

    const result = await readCiLogsHandler({
      branch: "main",
      event: "push",
      repo: "org/other",
    });

    expect(runTDCli).toHaveBeenCalledWith(
      ["repo", "workflow-runs", "--repo", "org/other", "--branch", "main", "--event", "push"],
      "fetch workflow runs"
    );
    expect(result.workflowRuns).toEqual([{ id: 2 }]);
  });

  it("omits filters that are unset", async () => {
    runTDCli.mockResolvedValue({ workflow_runs: [] });

    await readCiLogsHandler({});

    expect(runTDCli).toHaveBeenCalledWith(["repo", "workflow-runs"], "fetch workflow runs");
  });
});

describe("repo.read_ci_logs — #1025 regression: explicit null args", () => {
  it("accepts null for every optional field and lists workflow runs", async () => {
    runTDCli.mockResolvedValue({ workflow_runs: [] });

    const result = await readCiLogsHandler({
      prNumber: null,
      all: null,
      repo: null,
      includeRuns: null,
      branch: null,
      event: null,
    });

    expect(runTDCli).toHaveBeenCalledWith(["repo", "workflow-runs"], "fetch workflow runs");
    expect(result.workflowRuns).toEqual([]);
  });

  it("treats null filters as absent when fetching runs", async () => {
    runTDCli.mockResolvedValue({ workflow_runs: [{ id: 3 }] });

    await readCiLogsHandler({ branch: null, event: null, repo: null });

    expect(runTDCli).toHaveBeenCalledWith(["repo", "workflow-runs"], "fetch workflow runs");
  });

  it("treats null prNumber as omitted for the runs listing", async () => {
    runTDCli.mockResolvedValue({ workflow_runs: [] });

    await readCiLogsHandler({ prNumber: null, includeRuns: null });

    expect(runTDCli).toHaveBeenCalledTimes(1);
    expect(runTDCli).toHaveBeenCalledWith(["repo", "workflow-runs"], "fetch workflow runs");
  });
});
