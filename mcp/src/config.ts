import dotenv from "dotenv";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";
import { execSync } from "child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

dotenv.config({
  path: path.resolve(__dirname, "../.env"),
  quiet: true
});

function getGithubToken(): string | undefined {
  if (process.env.GITHUB_TOKEN) {
    return process.env.GITHUB_TOKEN;
  }
  try {
    const token = execSync("gh auth token", { encoding: "utf-8", stdio: ["ignore", "pipe", "ignore"] }).trim();
    if (token) {
      return token;
    }
  } catch (e) { throw e; }
  return undefined;
}

let cachedDynamicConfig: any = null;

/**
 * Explicitly initializes dynamic configuration from the Python CLI.
 * Should be called once during server startup.
 */
export function initializeConfig() {
  if (cachedDynamicConfig !== null) {
    return cachedDynamicConfig;
  }

  try {
    // Attempt to load core properties from the Python CLI to avoid duplication
    const cmd = `td-cli config view`;
    const output = execSync(cmd, {
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"]
    });
    cachedDynamicConfig = JSON.parse(output);
    return cachedDynamicConfig;
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    const errorPrefix = `CRITICAL: Failed to load dynamic config from Python CLI. Ensure Python 3 is installed and boomtick-pkg/cli is in your PYTHONPATH. Details: ${message}`;

    if (process.env.NODE_ENV === "development" || process.env.CI === "true") {
      throw new Error(errorPrefix);
    } else {
      console.warn(errorPrefix);
    }
    // Set an empty object to prevent repeated attempts if initialization fails in non-blocking mode
    cachedDynamicConfig = {};
  }
  return cachedDynamicConfig;
}

function findRepoRoot() {
  if (process.env.BOOMTICK_REPO_PATH) {
    return process.env.BOOMTICK_REPO_PATH;
  }

  // Traverse up to find workspace.json or .git
  let current = __dirname;
  while (current !== path.parse(current).root) {
    if (fs.existsSync(path.join(current, "workspace.json")) || fs.existsSync(path.join(current, ".git"))) {
      return current;
    }
    current = path.dirname(current);
  }
  // Fallback to the monolithic relative path if discovery fails
  return path.resolve(__dirname, "../../../");
}

export const config = {
  get githubToken() { return getGithubToken(); },
  get githubOwner() {
    if (process.env.GITHUB_OWNER) return process.env.GITHUB_OWNER;
    const repoString = cachedDynamicConfig?.github_repo;
    if (typeof repoString !== "string" || !repoString.includes("/")) {
      throw new Error("GITHUB_OWNER must be set via environment variable or project_config.json");
    }
    return repoString.split("/")[0];
  },
  get githubRepo() {
    if (process.env.GITHUB_REPO) return process.env.GITHUB_REPO;
    const repoString = cachedDynamicConfig?.github_repo;
    if (typeof repoString !== "string" || !repoString.includes("/")) {
      throw new Error("GITHUB_REPO must be set via environment variable or project_config.json");
    }
    return repoString.split("/")[1];
  },
  get repoPath() {
    return findRepoRoot();
  },
  get defaultBaseBranch() {
    return process.env.DEFAULT_BASE_BRANCH || cachedDynamicConfig?.base_branch?.split("/").pop() || "main";
  },
  get viteBasePath() {
    const path = process.env.VITE_BASE_PATH || cachedDynamicConfig?.vite_base_path;
    if (!path) {
      throw new Error("VITE_BASE_PATH must be set via environment variable or project_config.json");
    }
    return path;
  },
  get ghPath() {
    return process.env.GH_PATH || cachedDynamicConfig?.gh_path || "gh";
  }
};
