import dotenv from "dotenv";
import path from "path";
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
  } catch (e) {}
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
    const pythonPath = process.env.PYTHONPATH ? `PYTHONPATH=${process.env.PYTHONPATH} ` : "";
    const cmd = `${pythonPath}python3 -m dev_tools.cli config view`;
    const output = execSync(cmd, {
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"],
      cwd: path.resolve(__dirname, "../../cli")
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

export const config = {
  get githubToken() { return getGithubToken(); },
  get githubOwner() {
    const [defaultOwner] = (cachedDynamicConfig?.github_repo || "arii/tech-dancer").split("/");
    return process.env.GITHUB_OWNER || defaultOwner;
  },
  get githubRepo() {
    const [, defaultRepo] = (cachedDynamicConfig?.github_repo || "arii/tech-dancer").split("/");
    return process.env.GITHUB_REPO || defaultRepo;
  },
  get repoPath() {
    return process.env.BOOMTICK_REPO_PATH || path.resolve(__dirname, "../../../");
  },
  get defaultBaseBranch() {
    return process.env.DEFAULT_BASE_BRANCH || cachedDynamicConfig?.base_branch?.split("/").pop() || "main";
  },
  get viteBasePath() {
    return process.env.VITE_BASE_PATH || cachedDynamicConfig?.vite_base_path || "/tech-dancer/";
  },
  get ghPath() {
    return process.env.GH_PATH || cachedDynamicConfig?.gh_path || "gh";
  }
};

