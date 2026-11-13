import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../lib/tdCli.js", () => ({ runTDCli: vi.fn() }));
vi.mock("../lib/session_manager.js", () => ({ recordToolReceipt: vi.fn() }));
vi.mock("../lib/skills.js", () => ({ listSkills: vi.fn().mockResolvedValue([]), readSkill: vi.fn() }));
vi.mock("../lib/tdHealth.js", () => ({ getTdPreflight: vi.fn(() => null) }));
vi.mock("../lib/ragHealth.js", () => ({ getRagHealth: vi.fn(() => ({ indexAvailable: false })) }));
vi.mock("../config/repo.js", () => ({
  readPerRepoGithubRepo: vi.fn(() => null),
  findRepoRoot: vi.fn(() => "/mock/repo"),
}));

import * as tdCliModule from "../lib/tdCli.js";
import { repoContextHandler } from "./repo.context.js";

const tdMock = () => vi.mocked(tdCliModule.runTDCli);

describe("repo_context mode routing", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("routes scope=all to td multi-repo status and returns the ecosystem payload", async () => {
    tdMock().mockResolvedValueOnce({ repos: [{ path: "/r" }], total: 1 });

    const res = await repoContextHandler({ scope: "all" });

    expect(tdMock()).toHaveBeenCalledWith(["multi-repo", "status"], "fetch multi-repo context");
    expect(res.ecosystem).toBe(true);
    expect(res.repos).toEqual([{ path: "/r" }]);
    expect(res.total).toBe(1);
  });

  it("reads single-repo context by default without any td call", async () => {
    const res = await repoContextHandler({});

    expect(tdMock()).not.toHaveBeenCalled();
    expect(res.status).toBe("success");
    expect(res.server).toBeDefined();
    expect(res.ecosystem).toBeNull();
  });

  it("rejects an unknown scope value", async () => {
    await expect(
      repoContextHandler({ scope: "everything" as unknown as "all" }),
    ).rejects.toThrow();
    expect(tdMock()).not.toHaveBeenCalled();
  });
});
