import { z } from "zod";
import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";
import * as yaml from "yaml";
import { config } from "../config.js";
import { readPerRepoGithubRepo } from "../config/repo.js";
import { runTDCli } from "../lib/tdCli.js";
import { recordToolReceipt } from "../lib/session_manager.js";
import { listSkills, readSkill } from "../lib/skills.js";
import type { SkillSummary } from "../lib/skills.js";
import { getTdPreflight } from "../lib/tdHealth.js";
import { getRagHealth } from "../lib/ragHealth.js";
import {
  RepoContextInputSchema,
  RepoContextResponseSchema,
  AgentContractConfigSchema,
} from "./contract.js";

export { RepoContextInputSchema };

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

  const packageName =
    typeof projectConfig.packageName === "string" ? projectConfig.packageName : "boomtick";
  return {
    packageName,
    gitCommit,
    config: projectConfig,
  };
};

export class RepoResolutionError extends Error {
  constructor(repo: string) {
    super(
      `Unknown repository "${repo}": not resolvable via "td multi-repo status", not registered in ecosystem_repos (project_config.json), and no matching sibling directory of the server cwd exists. Register the repo in project_config.json ecosystem_repos or pass an explicit path.`
    );
    this.name = "RepoResolutionError";
  }
}

/**
 * Match a repo name ("owner/name" or "name") against the project_config.json at
 * rootPath: either its own github_repo declaration (repo is the config root
 * itself) or an ecosystem_repos entry. Returns the resolved absolute path, or
 * null when there is no match / the config is unreadable.
 */
export function matchRepoInProjectConfig(rootPath: string, rawRepo: string): string | null {
  const repoName = rawRepo.includes("/") ? rawRepo.split("/")[1] : rawRepo;
  const projectConfigPath = path.join(rootPath, "project_config.json");
  if (!fs.existsSync(projectConfigPath)) {
    return null;
  }
  try {
    const parsed = JSON.parse(fs.readFileSync(projectConfigPath, "utf-8"));
    if (
      typeof parsed.github_repo === "string" &&
      (parsed.github_repo === rawRepo || parsed.github_repo.split("/")[1] === repoName)
    ) {
      return rootPath;
    }
    if (parsed.ecosystem_repos && typeof parsed.ecosystem_repos === "object") {
      for (const [key, relPath] of Object.entries(parsed.ecosystem_repos)) {
        const keyRepoName = key.includes("/") ? key.split("/")[1] : key;
        if (key === rawRepo || keyRepoName === repoName) {
          return path.resolve(rootPath, relPath as string);
        }
      }
    }
  } catch {
    // Unreadable config → no match from this root; caller fails loudly instead.
  }
  return null;
}

export async function resolveTargetRepoPath(args: {
  repo?: string | null;
}): Promise<string> {
  if (!args.repo) {
    return config.repoPath;
  }
  const rawRepo = args.repo.trim();
  let matchedPath: string | undefined;
  try {
    const output = await runTDCli(["multi-repo", "status", "-r", rawRepo], "find target repository");
    const matched = output.repos?.[0];
    if (matched?.path) {
      matchedPath = matched.path;
    }
  } catch {
    // Fallback if CLI unavailable
  }

  if (!matchedPath) {
    const repoName = rawRepo.includes("/") ? rawRepo.split("/")[1] : rawRepo;
    const cwdParent = path.resolve(process.cwd(), "..", repoName);
    const configParent = path.resolve(config.repoPath, "..", repoName);

    if (fs.existsSync(cwdParent)) {
      matchedPath = cwdParent;
    } else if (fs.existsSync(configParent)) {
      matchedPath = configParent;
    }
  }

  // The caller's own project_config.json is the next signal: it names the repo
  // the server runs in (github_repo) and any registered ecosystem repos.
  if (!matchedPath) {
    matchedPath = matchRepoInProjectConfig(config.repoPath, rawRepo) ?? undefined;
  }

  if (matchedPath) {
    return matchedPath;
  }

  // Fail loudly: an unresolvable repo name must never silently return this
  // server's own repo context under the caller's repo label.
  throw new RepoResolutionError(rawRepo);
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
    // .agent-context.json is gitignored, so `git log -- .agent-context.json`
    // has no commits to compare and a commit-ts check is always stale.
    // Freshness is an mtime question: was the file written after the
    // current HEAD commit landed?
    const headRes = execSync("git log -1 --format=%ct HEAD", {
      cwd: targetPath, encoding: "utf-8", stdio: ["pipe", "pipe", "ignore"],
    }).trim();
    const headTs = parseInt(headRes || "0", 10);
    if (headTs > 0 && contextMtime > 0 && contextMtime < headTs * 1000) {
      isStale = true;
      staleFiles.push("HEAD commit is newer than .agent-context.json mtime");
    }
  } catch {
    // Git unavailable: file presence is the only signal
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

/**
 * Server health (absorbed boomtick_health): always included in repo_context
 * responses — health is repo metadata, not a separate tool call.
 */
export function getServerHealth() {
  return {
    githubOwner: config.githubOwner,
    githubRepo: config.githubRepo,
    repoPath: config.repoPath,
    readOnly: !config.githubToken,
    ghPath: config.ghPath,
    // td availability recorded by the startup preflight; null when the
    // preflight has not run yet.
    tdAvailable: getTdPreflight()?.available ?? null,
    // Deterministic RAG index/canary state for this repo (silent 0-hit
    // indexes and never-built indexes surface here instead of being
    // diagnosed by hand).
    rag: getRagHealth(config.repoPath || process.cwd()),
  };
}

export async function repoContextHandler(
  args: z.input<typeof RepoContextInputSchema>
): Promise<Record<string, unknown>> {
  const params = RepoContextInputSchema.parse(args);

  // Ecosystem / multi-repo request (scope="all")
  if (params.scope === "all") {
    const output = await runTDCli(["multi-repo", "status"], "fetch multi-repo context");
    recordToolReceipt(process.cwd(), "repo.context", { scope: "all" });
    return RepoContextResponseSchema.parse({
      status: "success",
      ecosystem: true,
      repos: output.repos ?? [],
      total: output.total ?? (output.repos?.length ?? 0),
    });
  }

  const targetPath = params.repo
    ? await resolveTargetRepoPath({ repo: params.repo })
    : config.repoPath;

  const context = loadStandaloneAgentContext(targetPath);
  const configSection = { ...context.config };
  delete configSection.submodules;

  const result = {
    status: "success",
    path: targetPath,
    repo: params.repo ?? readPerRepoGithubRepo(targetPath) ?? undefined,
    packageName: context.packageName,
    gitCommit: context.gitCommit,
    config: configSection,
    agentContract: readAgentContractSection(targetPath),
    packageScripts: getPackageScriptsSection(targetPath),
    vectorIndex: getVectorIndexStatus(targetPath),
    skills: await listSkills(targetPath),
    server: getServerHealth(),
  };

  if (params.skill) {
    const skillBody = { name: params.skill, body: await readSkill(targetPath, params.skill) };
    recordToolReceipt(targetPath, "repo.context", {
      repo: params.repo ?? targetPath,
      skill: params.skill,
    });
    return RepoContextResponseSchema.parse({ ...result, skill: skillBody });
  }

  recordToolReceipt(targetPath, "repo.context", {
    repo: params.repo ?? targetPath,
  });
  return RepoContextResponseSchema.parse(result);
}
