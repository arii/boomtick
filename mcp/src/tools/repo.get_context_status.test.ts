import { describe, expect, it } from "vitest";
import { getContextStatusHandler } from "./repo.get_context_status.js";

describe("repo.get_context_status Tool Handler", () => {
  it("should return context status for default workspace", async () => {
    const res = await getContextStatusHandler({});
    expect(res).toHaveProperty("warm");
    expect(typeof res.warm).toBe("boolean");
    expect(res).toHaveProperty("path");
    expect(res.path).toContain(".agent-context.json");
    expect(Array.isArray(res.staleFiles)).toBe(true);
  });

  it("should accept repoPath argument", async () => {
    const res = await getContextStatusHandler({ repoPath: process.cwd() });
    expect(res).toHaveProperty("warm");
    expect(res.path).toContain(".agent-context.json");
  });
});
