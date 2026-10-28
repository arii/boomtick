import { z } from "zod";
import { config } from "../config.js";
import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";

export interface AgentContext {
  packageName: string;
  gitCommit: string;
  config: Record<string, unknown>;
}

export const loadStandaloneAgentContext = (repoRoot: string = process.cwd()): AgentContext => {
  const configPath = path.join(repoRoot, "project_config.json");
  let projectConfig: Record<string, unknown> = {};

  if (fs.existsSync(configPath)) {
    try {
      projectConfig = JSON.parse(fs.readFileSync(configPath, "utf-8"));
    } catch (e) {
      console.warn(`[MCP Warning] Failed to parse ${configPath}:`, e);
    }
  }

  let gitCommit = "unknown";
  try {
    gitCommit = execSync("git rev-parse HEAD", { cwd: repoRoot, encoding: "utf-8" }).trim();
  } catch {
    // Fallback if git is unavailable
  }

  return {
    packageName: (projectConfig.packageName as string) ?? "boomtick",
    gitCommit,
    config: projectConfig,
  };
};

export const ReadAgentContextInputSchema = z.object({
  repoPath: z.string().optional(),
});

export async function readAgentContextHandler(args: z.infer<typeof ReadAgentContextInputSchema>) {
  const repoRoot = args?.repoPath || config.repoPath;
  const context = loadStandaloneAgentContext(repoRoot);
  const result: any = {
    status: "success",
    ...context
  };
  delete result.submodules;
  if (result.config) {
    delete result.config.submodules;
  }
  return result;
}
