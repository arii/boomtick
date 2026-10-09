import { describe, it, expect } from "vitest";
import { normalizeArguments } from "./param_utils.js";

describe("normalizeArguments", () => {
  it("should return empty object when input is null or undefined", () => {
    expect(normalizeArguments(null)).toEqual({});
    expect(normalizeArguments(undefined)).toEqual({});
  });

  it("should convert snake_case keys to camelCase", () => {
    const input = { pr_number: 123, issue_number: 456, worktree_path: "/tmp/worktree" };
    const result = normalizeArguments(input);
    expect(result.prNumber).toBe(123);
    expect(result.issueNumber).toBe(456);
    expect(result.worktreePath).toBe("/tmp/worktree");
  });

  it("should coerce numeric strings to integers for number fields", () => {
    const input = { prNumber: "123", limit: "50", timeout_seconds: "30" };
    const result = normalizeArguments(input);
    expect(result.prNumber).toBe(123);
    expect(result.limit).toBe(50);
    expect(result.timeoutSeconds).toBe(30);
  });

  it("should harmonize branch and branchName aliases", () => {
    expect(normalizeArguments({ branch: "feature-x" })).toEqual({ branch: "feature-x", branchName: "feature-x" });
    expect(normalizeArguments({ branchName: "feature-y" })).toEqual({ branchName: "feature-y", branch: "feature-y" });
  });

  it("should harmonize pr and issue aliases", () => {
    expect(normalizeArguments({ pr: 99 })).toEqual({ pr: 99, prNumber: 99 });
    expect(normalizeArguments({ issue: 88 })).toEqual({ issue: 88, issueNumber: 88 });
  });
});
