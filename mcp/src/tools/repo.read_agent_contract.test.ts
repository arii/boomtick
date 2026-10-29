import { describe, expect, it } from "vitest";
import path from "path";
import { readAgentContractHandler } from "./repo.read_agent_contract.js";

describe("repo.read_agent_contract Tool Handler", () => {
  it("should read agent contract from current workspace by default", async () => {
    const res = await readAgentContractHandler({});
    expect(res.status).toBe("success");
    expect(res.content).toContain("# Agent Contract");
    expect(res.path).toContain("AGENT_CONTRACT.md");
  });

  it("should accept repoPath argument", async () => {
    const rootPath = path.resolve(process.cwd(), "..");
    const res = await readAgentContractHandler({ repoPath: rootPath });
    expect(res.status).toBe("success");
    expect(res.content).toBeDefined();
    expect(res.path).toContain("AGENT_CONTRACT.md");
  });
});
