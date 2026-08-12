import { describe, expect, it } from "vitest";
import { loadStandaloneAgentContext } from "../lib/td-cli.js";

describe("Standalone Agent Context Loader", () => {
  it("should load agent context without submodule references", () => {
    const context = loadStandaloneAgentContext(process.cwd());
    expect(context).toHaveProperty("packageName");
    expect(context).toHaveProperty("gitCommit");
    expect(context).not.toHaveProperty("submodules");
  });
});
