import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { execSync } from "child_process";

vi.mock("child_process", () => ({
  execSync: vi.fn(),
}));

describe("config", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    vi.resetModules();
    process.env = { ...originalEnv };
    vi.mocked(execSync).mockReset();
    vi.mocked(execSync).mockReturnValue("{}");
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  describe("initializeConfig", () => {
    it("should load dynamic config from td-cli config view", async () => {
      const mockConfig = { github_repo: "owner/repo", base_branch: "origin/main", vite_base_path: "/app/" };
      vi.mocked(execSync).mockReturnValue(JSON.stringify(mockConfig));

      const { initializeConfig } = await import("./config.js");
      const result = initializeConfig();

      expect(execSync).toHaveBeenCalledWith("td-cli config view", expect.anything());
      expect(result).toEqual(mockConfig);
    });

    it("should return cached dynamic config on subsequent calls", async () => {
      const mockConfig = { github_repo: "owner/repo" };
      vi.mocked(execSync).mockReturnValue(JSON.stringify(mockConfig));

      const { initializeConfig } = await import("./config.js");
      const result1 = initializeConfig();
      const result2 = initializeConfig();

      expect(result1).toBe(result2);
      expect(execSync).toHaveBeenCalledTimes(1);
    });

    it("should throw critical error when execSync fails in development or CI", async () => {
      process.env.NODE_ENV = "development";
      vi.mocked(execSync).mockImplementation(() => {
        throw new Error("Command failed");
      });

      const { initializeConfig } = await import("./config.js");
      expect(() => initializeConfig()).toThrow(/CRITICAL: Failed to load dynamic config/);
    });

    it("should log warning and set empty config when execSync fails in production", async () => {
      process.env.NODE_ENV = "production";
      process.env.CI = "false";
      const consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

      vi.mocked(execSync).mockImplementation(() => {
        throw new Error("Command failed");
      });

      const { initializeConfig } = await import("./config.js");
      const result = initializeConfig();

      expect(result).toEqual({});
      expect(consoleWarnSpy).toHaveBeenCalledWith(expect.stringContaining("CRITICAL: Failed to load dynamic config"));
      consoleWarnSpy.mockRestore();
    });
  });

  describe("config object getters", () => {
    it("should resolve githubToken from process.env or gh CLI fallback", async () => {
      process.env.GITHUB_TOKEN = "env-token-123";
      const { config } = await import("./config.js");
      expect(config.githubToken).toBe("env-token-123");

      delete process.env.GITHUB_TOKEN;
      vi.mocked(execSync).mockReturnValue("gh-cli-token\n");
      expect(config.githubToken).toBe("gh-cli-token");

      vi.mocked(execSync).mockImplementation(() => {
        throw new Error("gh not found");
      });
      expect(config.githubToken).toBeUndefined();
    });

    it("should resolve githubOwner and githubRepo from env or cached config", async () => {
      process.env.GITHUB_OWNER = "custom-owner";
      process.env.GITHUB_REPO = "custom-repo";
      const { config } = await import("./config.js");

      expect(config.githubOwner).toBe("custom-owner");
      expect(config.githubRepo).toBe("custom-repo");
    });

    it("should throw when githubOwner / githubRepo cannot be determined", async () => {
      delete process.env.GITHUB_OWNER;
      delete process.env.GITHUB_REPO;
      vi.mocked(execSync).mockImplementation(() => {
        throw new Error("td-cli failed");
      });

      process.env.NODE_ENV = "production";
      process.env.CI = "false";
      vi.spyOn(console, "warn").mockImplementation(() => {});

      const { config, initializeConfig } = await import("./config.js");
      initializeConfig();

      expect(() => config.githubOwner).toThrow("GITHUB_OWNER must be set via environment variable or project_config.json");
      expect(() => config.githubRepo).toThrow("GITHUB_REPO must be set via environment variable or project_config.json");
    });

    it("should resolve repoPath from BOOMTICK_REPO_PATH or findRepoRoot fallback", async () => {
      process.env.BOOMTICK_REPO_PATH = "/custom/repo/path";
      const { config } = await import("./config.js");
      expect(config.repoPath).toBe("/custom/repo/path");
    });

    it("should resolve defaultBaseBranch, viteBasePath, and ghPath", async () => {
      process.env.DEFAULT_BASE_BRANCH = "develop";
      process.env.VITE_BASE_PATH = "/base/";
      process.env.GH_PATH = "/usr/bin/gh";

      const { config } = await import("./config.js");
      expect(config.defaultBaseBranch).toBe("develop");
      expect(config.viteBasePath).toBe("/base/");
      expect(config.ghPath).toBe("/usr/bin/gh");
    });

    it("should throw when viteBasePath is missing", async () => {
      delete process.env.VITE_BASE_PATH;
      process.env.NODE_ENV = "production";
      process.env.CI = "false";
      vi.spyOn(console, "warn").mockImplementation(() => {});

      const { config, initializeConfig } = await import("./config.js");
      initializeConfig();

      expect(() => config.viteBasePath).toThrow("VITE_BASE_PATH must be set via environment variable or project_config.json");
    });
  });
});
