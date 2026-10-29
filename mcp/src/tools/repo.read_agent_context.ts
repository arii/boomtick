import { z } from "zod";
import { config } from "../config.js";
import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";
import { runTDCli } from "./jules/shared.js";

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

export async function resolveTargetRepoPath(args: {
  path?: string | null;
  repoPath?: string | null;
  repo?: string | null;
}): Promise<string> {
  if (args.repo) {
    let matchedPath: string | undefined;
    try {
      const output = await runTDCli(["multi-repo", "status", "-r", args.repo], "find target repository");
      const matched = output.repos?.[0];
      if (matched?.path) {
        matchedPath = matched.path;
      }
    } catch {
      // Fallback if CLI unavailable
    }

    if (!matchedPath) {
      const repoName = args.repo.includes("/") ? args.repo.split("/")[1] : args.repo;
      const cwdParent = path.resolve(process.cwd(), "..", repoName);
      const configParent = path.resolve(config.repoPath, "..", repoName);

      if (fs.existsSync(cwdParent)) {
        matchedPath = cwdParent;
      } else if (fs.existsSync(configParent)) {
        matchedPath = configParent;
      }
    }

    if (matchedPath) {
      return matchedPath;
    }
  }

  const explicitPath = args.path || args.repoPath;
  if (explicitPath) {
    return path.resolve(explicitPath);
  }

  return config.repoPath;
}

export const ReadAgentContextInputSchema = z.object({
  path: z.string().optional().describe("Local filesystem path to target repository root"),
  repoPath: z.string().optional().describe("Alias for path to target repository root"),
  repo: z.string().optional().describe("Repository name override (e.g. arii/portfolio or portfolio)"),
  repos: z.array(z.string()).optional().describe("List of repository names to fetch context for"),
  all: z.boolean().optional().describe("Whether to fetch context across all discovered ecosystem repositories"),
});

export async function readAgentContextHandler(args: z.infer<typeof ReadAgentContextInputSchema>) {
  // 1. Ecosystem / Multi-repo request
  if (args.all || (args.repos && args.repos.length > 0)) {
    const cliArgs = ["multi-repo", "status"];
    if (args.repos) {
      for (const r of args.repos) {
        cliArgs.push("-r", r);
      }
    }
    const output = await runTDCli(cliArgs, "fetch multi-repo context");
    return {
      status: "success",
      ecosystem: true,
      repos: output.repos ?? [],
      total: output.total ?? (output.repos?.length ?? 0)
    };
  }

  // 2. Specific repository name override
  if (args.repo) {
    const matchedPath = await resolveTargetRepoPath({ repo: args.repo });
    if (matchedPath && matchedPath !== config.repoPath) {
      const context = loadStandaloneAgentContext(matchedPath);
      return {
        status: "success",
        repo: args.repo,
        path: matchedPath,
        ...context
      };
    }
  }

  // 3. Specific filesystem path or default
  const targetPath = await resolveTargetRepoPath(args);
  const context = loadStandaloneAgentContext(targetPath);
  const result: any = {
    status: "success",
    path: targetPath,
    ...context
  };
  if (args?.repo) {
    result.repo = args.repo;
  }
  delete result.submodules;
  if (result.config) {
    delete result.config.submodules;
  }
  return result;
}
