import { describe, it, expect } from "vitest";
import path from "path";

// Simple test to verify environment and vitest setup
describe("Basic Environment", () => {
  it("should have a valid repo path", () => {
    const repoPath = process.env.BOOMTICK_REPO_PATH || "/app";
    expect(repoPath).toBeDefined();
    expect(path.isAbsolute(repoPath)).toBe(true);
  });
});
