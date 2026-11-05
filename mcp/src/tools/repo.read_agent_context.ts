import { z } from "zod";
import { config } from "../config.js";
import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";
import * as yaml from "yaml";
import { runTDCli } from "../lib/tdCli.js";
import { listSkills, readSkill } from "../lib/skills.js";
import { AgentContractConfigSchema } from "./contract.js";

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

export function readAgentContractSection(targetPath: string): {
  found: boolean;
  path: string;
  content: string | null;
  config: Record<string, unknown> | null;
} {
  const contractPath = path.join(targetPath, ".agents", "AGENT_CONTRACT.md");
  if (!fs.existsSync(contractPath)) {
    return { found: false, path: contractPath, content: null, config: null };
  }
  const rawContent = fs.readFileSync(contractPath, "utf-8");
  const frontMatterMatch = rawContent.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
  let parsedConfigRaw: Record<string, unknown> | null = null;
  let markdownBody = rawContent;
  if (frontMatterMatch) {
    markdownBody = rawContent.slice(frontMatterMatch[0].length);
    try {
      const parsedYaml = yaml.parse(frontMatterMatch[1]);
      if (parsedYaml && typeof parsedYaml === "object") {
        parsedConfigRaw = parsedYaml as Record<string, unknown>;
      }
    } catch {
      // Fall through to raw body with default config
    }
  }
  if (!parsedConfigRaw) {
    const jsonConfigPath = path.join(targetPath, ".agents", "agent-config.json");
    if (fs.existsSync(jsonConfigPath)) {
      try {
        const parsedJson = JSON.parse(fs.readFileSync(jsonConfigPath, "utf-8"));
        if (parsedJson && typeof parsedJson === "object") {
          parsedConfigRaw = parsedJson as Record<string, unknown>;
        }
      } catch {
        // Fall through to default config
      }
    }
  }
  const parsed = AgentContractConfigSchema.parse(parsedConfigRaw || {});
  return { found: true, path: contractPath, content: markdownBody, config: parsed };
}

export function getPackageScriptsSection(targetPath: string): Record<string, string> {
  const packageJsonPath = path.join(targetPath, "package.json");
  if (!fs.existsSync(packageJsonPath)) {
    return {};
  }
  try {
    const pkg = JSON.parse(fs.readFileSync(packageJsonPath, "utf-8"));
    return (pkg.scripts && typeof pkg.scripts === "object" ? pkg.scripts : {}) as Record<string, string>;
  } catch {
    return {};
  }
}

export function getVectorIndexStatus(targetPath: string): {
  warm: boolean;
  lastWarmedAt: string | null;
  path: string;
  staleFiles: string[];
} {
  const contextFile = path.join(targetPath, ".agent-context.json");
  if (!fs.existsSync(contextFile)) {
    return { warm: false, lastWarmedAt: null, path: contextFile, staleFiles: [".agent-context.json missing"] };
  }
  let lastWarmedAt: string | null = null;
  let contextMtime = 0;
  try {
    const stats = fs.statSync(contextFile);
    contextMtime = stats.mtimeMs;
    lastWarmedAt = stats.mtime.toISOString();
  } catch {
    // stat failed
  }
  let isStale = false;
  const staleFiles: string[] = [];
  try {
    const gitRes = execSync("git log -1 --format=%ct -- .agent-context.json", {
      cwd: targetPath, encoding: "utf-8", stdio: ["pipe", "pipe", "ignore"],
    }).trim();
    const contextCommitTs = parseInt(gitRes || "0", 10);
    const headRes = execSync("git log -1 --format=%ct HEAD", {
      cwd: targetPath, encoding: "utf-8", stdio: ["pipe", "pipe", "ignore"],
    }).trim();
    const headTs = parseInt(headRes || "0", 10);
    if (headTs > contextCommitTs) {
      isStale = true;
      staleFiles.push("HEAD commit is newer than .agent-context.json commit");
    }
  } catch {
    // Git check fallback
  }
  const keyFiles = ["package.json", "project_config.json", "cli/dev_tools/cli-schema.json", "cli/dev_tools/cli-commands-schema.json"];
  for (const keyFile of keyFiles) {
    const fullPath = path.join(targetPath, keyFile);
    if (fs.existsSync(fullPath)) {
      try {
        if (fs.statSync(fullPath).mtimeMs > contextMtime) {
          isStale = true;
          if (!staleFiles.includes(keyFile)) {
            staleFiles.push(keyFile);
          }
        }
      } catch {
        // ignore
      }
    }
  }
  return { warm: !isStale, lastWarmedAt, path: contextFile, staleFiles };
}

export const ReadAgentContextInputSchema = z.object({
  path: z.string().optional().describe("Local filesystem path to target repository root"),
  repoPath: z.string().optional().describe("Alias for path to target repository root"),
  repo: z.string().optional().describe("Repository name override (e.g. arii/portfolio or portfolio)"),
  repos: z.array(z.string()).optional().describe("List of repository names to fetch context for"),
  all: z.boolean().optional().describe("Whether to fetch context across all discovered ecosystem repositories"),
  skillName: z.string().optional().describe("Optional skill name: return its SKILL.md body too (absorbs skill_read)."),
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
      const named: any = {
        status: "success",
        repo: args.repo,
        path: matchedPath,
        ...context,
        agent_contract: readAgentContractSection(matchedPath),
        package_scripts: getPackageScriptsSection(matchedPath),
        vector_index: getVectorIndexStatus(matchedPath),
        skills: await listSkills(matchedPath)
      };
      if (args.skillName) {
        named.skill = { name: args.skillName, body: await readSkill(matchedPath, args.skillName) };
      }
      return named;
    }
  }

  // 3. Specific filesystem path or default
  const targetPath = await resolveTargetRepoPath(args);
  const context = loadStandaloneAgentContext(targetPath);
  const result: any = {
    status: "success",
    path: targetPath,
    ...context,
    agent_contract: readAgentContractSection(targetPath),
    package_scripts: getPackageScriptsSection(targetPath),
    vector_index: getVectorIndexStatus(targetPath),
    skills: await listSkills(targetPath)
  };
  if (args.skillName) {
    result.skill = { name: args.skillName, body: await readSkill(targetPath, args.skillName) };
  }
  if (args?.repo) {
    result.repo = args.repo;
  }
  delete result.submodules;
  if (result.config) {
    delete result.config.submodules;
  }
  return result;
}
