import { describe, expect, it } from "vitest";
import { MCP_TOOLS, MCP_PROMPTS } from "./definitions.js";

// #1026 regression: MCP clients reject tool names outside
// ^[a-zA-Z0-9_-]{1,64}$ at registration (Antigravity CLI dropped all
// 17 dot-notated tools at startup). Tool names must stay underscore- or
// dash-notated and within the length cap.
const MCP_CLIENT_NAME_PATTERN = /^[a-zA-Z0-9_-]{1,64}$/;

describe("MCP tool-name compliance (#1026)", () => {
  it("every registered tool name matches the MCP client naming regex", () => {
    expect(MCP_TOOLS.length).toBeGreaterThan(0);

    const violations = MCP_TOOLS.filter((tool) => !MCP_CLIENT_NAME_PATTERN.test(tool.name));
    expect(violations.map((tool) => tool.name)).toEqual([]);
  });

  it("no tool name contains a dot", () => {
    const dotted = MCP_TOOLS.filter((tool) => tool.name.includes("."));
    expect(dotted.map((tool) => tool.name)).toEqual([]);
  });

  it("tool names are unique", () => {
    const names = MCP_TOOLS.map((tool) => tool.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it("every tool carries non-empty input and output JSON schemas", () => {
    for (const tool of MCP_TOOLS) {
      expect(tool.inputSchema, `${tool.name} inputSchema`).toBeDefined();
      expect(tool.outputSchema, `${tool.name} outputSchema`).toBeDefined();
    }
  });
});

describe("MCP prompt-name compliance (#1026)", () => {
  it("every registered prompt name matches the MCP client naming regex", () => {
    const violations = MCP_PROMPTS.filter((prompt) => !MCP_CLIENT_NAME_PATTERN.test(prompt.name));
    expect(violations.map((prompt) => prompt.name)).toEqual([]);
  });
});
