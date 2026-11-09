import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";
import { findRepoRoot } from "./config/repo.js";
import { getGithubToken } from "./config/github.js";
import { resolveRepo } from "./lib/git.js";
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

export function resolveStackEnvPath(): string {
  return (
    process.env.REMOTE_SERVER_ENV_PATH ||
    process.env.STACK_ENV_PATH ||
    ""
  );
}

export function loadStackEnv(explicitPath?: string): void {
  const targetPath = explicitPath || resolveStackEnvPath();
  if (!targetPath || !fs.existsSync(targetPath)) {
    return;
  }

  try {
    const content = fs.readFileSync(targetPath, "utf-8");
    const lines = content.split(/\r?\n/);
    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line || line.startsWith("#")) {
        continue;
      }
      const eqIdx = line.indexOf("=");
      if (eqIdx === -1) {
        continue;
      }
      const key = line.slice(0, eqIdx).trim();
      let value = line.slice(eqIdx + 1).trim();

      // Strip surrounding quotes if present
      if (
        (value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1);
      }

      // Do not overwrite existing environment variables
      if (process.env[key] === undefined) {
        process.env[key] = value;
      }
    }
  } catch {
    // Gracefully ignore reading errors
  }
}

// Load stack .env on startup
loadStackEnv();

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
    try {
      return resolveRepo().split("/")[0];
    } catch {
      throw new Error("GITHUB_OWNER must be set via environment variable or project_config.json");
    }
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
    try {
      return resolveRepo().split("/")[1];
    } catch {
      throw new Error("GITHUB_REPO must be set via environment variable or project_config.json");
    }
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
