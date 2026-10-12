import { describe, it, expect } from "vitest";
import { normalizeArguments } from "./param_utils.js";

describe("param_utils.normalizeArguments", () => {
  it("should convert snake_case keys to camelCase", () => {
    const input = {
      pr_number: 123,
      issue_number: 456,
      worktree_path: "/tmp/worktree",
      base_branch: "main",
    };
    const output = normalizeArguments(input);
    expect(output).toEqual({
      prNumber: 123,
      issueNumber: 456,
      worktreePath: "/tmp/worktree",
      baseBranch: "main",
    });
  });

  it("should coerce numeric strings for prNumber and issueNumber", () => {
    const input = {
      pr_number: "789",
      issue_number: "101",
    };
    const output = normalizeArguments(input);
    expect(output).toEqual({
      prNumber: 789,
      issueNumber: 101,
    });
  });

  it("should synchronize branch and branchName", () => {
    expect(normalizeArguments({ branch: "feat-x" })).toEqual({
      branch: "feat-x",
      branchName: "feat-x",
    });

    expect(normalizeArguments({ branch_name: "feat-y" })).toEqual({
      branchName: "feat-y",
      branch: "feat-y",
    });
  });

  it("should handle null or empty arguments safely", () => {
    expect(normalizeArguments(null)).toEqual({});
    expect(normalizeArguments(undefined)).toEqual({});
  });
});
