import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";
import { findRepoRoot } from "./config/repo.js";
import { getGithubToken } from "./config/github.js";
import { initializeConfig, getCachedDynamicConfig } from "./config/dynamic.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const envPath = path.resolve(__dirname, "../.env");
if (fs.existsSync(envPath) && typeof process.loadEnvFile === "function") {
  try {
    process.loadEnvFile(envPath);
  } catch {
    // Ignore if already loaded or invalid
  }
}

export { initializeConfig };

export const config = {
  get githubToken() {
    return getGithubToken();
  },
  get githubOwner() {
    const cachedDynamicConfig = getCachedDynamicConfig();
    const repoString = cachedDynamicConfig?.github_repo;
    if (typeof repoString === "string" && repoString.includes("/")) {
      return repoString.split("/")[0];
    }
    if (process.env.GITHUB_OWNER) return process.env.GITHUB_OWNER;
    const envRepo = process.env.GITHUB_REPOSITORY || process.env.GH_REPO;
    if (envRepo && envRepo.includes("/")) {
      return envRepo.split("/")[0];
    }
    throw new Error("GITHUB_OWNER must be set via environment variable or project_config.json");
  },
  get githubRepo() {
    const cachedDynamicConfig = getCachedDynamicConfig();
    const repoString = cachedDynamicConfig?.github_repo;
    if (typeof repoString === "string" && repoString.includes("/")) {
      return repoString.split("/")[1];
    }
    if (process.env.GITHUB_REPO) return process.env.GITHUB_REPO;
    const envRepo = process.env.GITHUB_REPOSITORY || process.env.GH_REPO;
    if (envRepo && envRepo.includes("/")) {
      return envRepo.split("/")[1];
    }
    throw new Error("GITHUB_REPO must be set via environment variable or project_config.json");
  },
  get repoPath() {
    return findRepoRoot();
  },
  get defaultBaseBranch() {
    const cachedDynamicConfig = getCachedDynamicConfig();
    return process.env.DEFAULT_BASE_BRANCH || cachedDynamicConfig?.base_branch?.split("/").pop() || "main";
  },
  get viteBasePath() {
    const cachedDynamicConfig = getCachedDynamicConfig();
    const pathValue = process.env.VITE_BASE_PATH || cachedDynamicConfig?.vite_base_path;
    if (!pathValue) {
      throw new Error("VITE_BASE_PATH must be set via environment variable or project_config.json");
    }
    return pathValue;
  },
  get ghPath() {
    const cachedDynamicConfig = getCachedDynamicConfig();
    return process.env.GH_PATH || cachedDynamicConfig?.gh_path || "gh";
  },
};
