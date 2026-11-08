import { execSync } from "child_process";
import { z } from "zod";
import { findRepoRoot } from "./repo.js";

const DynamicConfigSchema = z
  .object({
    github_repo: z.string().optional(),
    package_name: z.string().optional(),
    base_branch: z.string().optional(),
    vite_base_path: z.string().optional(),
    gh_path: z.string().optional(),
  })
  .catchall(z.unknown());

export type DynamicConfig = z.infer<typeof DynamicConfigSchema>;

let cachedDynamicConfig: DynamicConfig | null = null;
let dynamicConfigDegraded = false;

export function isDynamicConfigDegraded(): boolean {
  return dynamicConfigDegraded;
}

export function initializeConfig(targetCwd?: string): DynamicConfig {
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
    cachedDynamicConfig = DynamicConfigSchema.parse(JSON.parse(output));
    return cachedDynamicConfig;
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    const errorPrefix = `CRITICAL: Failed to load dynamic config from Python CLI. Ensure Python 3 is installed and cli is in your PYTHONPATH. Details: ${message}`;

    if (process.env.NODE_ENV === "development" || process.env.CI === "true") {
      throw new Error(errorPrefix);
    } else {
      console.warn(errorPrefix);
    }
    dynamicConfigDegraded = true;
    cachedDynamicConfig = {};
  }
  return cachedDynamicConfig;
}

export function getCachedDynamicConfig(): DynamicConfig | null {
  return cachedDynamicConfig;
}
