import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { execSync } from "child_process";

vi.mock("child_process", () => ({
  execSync: vi.fn(),
}));

const readPerRepoGithubRepoMock = vi.fn<(startDir?: string) => string | undefined>();

vi.mock("./config/repo.js", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./config/repo.js")>()),
  readPerRepoGithubRepo: (...args: [(string | undefined)?]) => readPerRepoGithubRepoMock(...args),
}));

// Independent regression tests for #1235 (PR #1237): githubOwner/githubRepo
// derive from the origin remote as a last resort. Explicit config still wins;
// no remote still throws the same message. Each test asserts the derive
// baseline first, so every test fails on pre-fix code.
describe("config origin-remote derive (issue #1235)", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    vi.resetModules();
    process.env = { ...originalEnv };
    vi.mocked(execSync).mockReset();
    // These tests pin the origin-remote derive path, so no per-repo declaration.
    readPerRepoGithubRepoMock.mockReset();
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  function mockOriginRemote(url = "https://github.com/test-owner/test-repo.git\n") {
    vi.mocked(execSync).mockImplementation(((command: unknown) => {
      if (
        typeof command === "string" &&
        command.includes("git remote get-url origin")
      ) {
        return url;
      }
      throw new Error("td failed");
    }) as typeof execSync);
  }

  async function initEmptyDynamicConfig() {
    process.env.NODE_ENV = "production";
    process.env.CI = "false";
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const { initializeConfig } = await import("./config.js");
    initializeConfig();
  }

  function clearRepoEnv() {
    delete process.env.GITHUB_OWNER;
    delete process.env.GITHUB_REPO;
    delete process.env.GITHUB_REPOSITORY;
    delete process.env.GH_REPO;
  }

  it("derives owner/repo from the origin remote when no config exists", async () => {
    clearRepoEnv();
    mockOriginRemote();
    await initEmptyDynamicConfig();

    const { config } = await import("./config.js");
    expect(config.githubOwner).toBe("test-owner");
    expect(config.githubRepo).toBe("test-repo");
  });

  it("keeps explicit env config ahead of the origin remote", async () => {
    clearRepoEnv();
    mockOriginRemote("https://github.com/remote-owner/remote-repo.git\n");
    await initEmptyDynamicConfig();

    const { config } = await import("./config.js");
    expect(config.githubOwner).toBe("remote-owner");

    process.env.GITHUB_OWNER = "explicit-owner";
    process.env.GITHUB_REPO = "explicit-repo";
    expect(config.githubOwner).toBe("explicit-owner");
    expect(config.githubRepo).toBe("explicit-repo");
  });

  it("throws the same message when no remote exists", async () => {
    clearRepoEnv();
    mockOriginRemote();
    await initEmptyDynamicConfig();

    const { config } = await import("./config.js");
    expect(config.githubOwner).toBe("test-owner");

    vi.resetModules();
    clearRepoEnv();
    vi.mocked(execSync).mockImplementation(() => {
      throw new Error("no remote");
    });
    await initEmptyDynamicConfig();

    const fresh = await import("./config.js");
    expect(() => fresh.config.githubOwner).toThrow(
      "GITHUB_OWNER must be set via environment variable or project_config.json"
    );
    expect(() => fresh.config.githubRepo).toThrow(
      "GITHUB_REPO must be set via environment variable or project_config.json"
    );
  });
});
