import { execSync } from "child_process";
import { findRepoRoot } from "./repo.js";

let cachedDynamicConfig: any = null;

export function initializeConfig(targetCwd?: string) {
  if (cachedDynamicConfig !== null) {
    return cachedDynamicConfig;
  }

  try {
    const cwd = findRepoRoot(targetCwd);
    const cmd = `td config view`;
    const output = execSync(cmd, {
      cwd,
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"],
    });
    cachedDynamicConfig = JSON.parse(output);
    return cachedDynamicConfig;
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    const errorPrefix = `CRITICAL: Failed to load dynamic config from Python CLI. Ensure Python 3 is installed and cli is in your PYTHONPATH. Details: ${message}`;

    if (process.env.NODE_ENV === "development" || process.env.CI === "true") {
      throw new Error(errorPrefix);
    } else {
      console.warn(errorPrefix);
    }
    cachedDynamicConfig = {};
  }
  return cachedDynamicConfig;
}

export function getCachedDynamicConfig(): any {
  return cachedDynamicConfig;
}
