import { describe, it, expect } from "vitest";
import { parseCommandString } from "./repo.run_tests.js";

describe("parseCommandString", () => {
  it("should split plain space-separated commands", () => {
    expect(parseCommandString("pnpm test")).toEqual(["pnpm", "test"]);
    expect(parseCommandString("pnpm run build --filter mcp")).toEqual(["pnpm", "run", "build", "--filter", "mcp"]);
  });

  it("should preserve double quoted arguments with spaces", () => {
    expect(parseCommandString('git commit -m "initial commit"')).toEqual(["git", "commit", "-m", "initial commit"]);
    expect(parseCommandString('vitest run -t "test name with spaces"')).toEqual(["vitest", "run", "-t", "test name with spaces"]);
  });

  it("should preserve single quoted arguments with spaces", () => {
    expect(parseCommandString("git commit -m 'initial commit'")).toEqual(["git", "commit", "-m", "initial commit"]);
  });

  it("should handle empty or whitespace-only string", () => {
    expect(parseCommandString("")).toEqual([""]);
    expect(parseCommandString("   ")).toEqual([""]);
  });
});
