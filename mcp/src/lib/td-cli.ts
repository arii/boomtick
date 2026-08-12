import { runCommand } from "../lib/shell.js";
import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";

export interface TDCliResponse {
  status: string;
  message?: string;
  [key: string]: any;
}

export interface AgentContext {
  packageName: string;
  gitCommit: string;
  config: Record<string, unknown>;
}

export const loadStandaloneAgentContext = (repoRoot: string = process.cwd()): AgentContext => {
  const configPath = path.join(repoRoot, "project_config.json");
  let config: Record<string, unknown> = {};

  if (fs.existsSync(configPath)) {
    try {
      config = JSON.parse(fs.readFileSync(configPath, "utf-8"));
    } catch (e) {
      console.warn(`[MCP Warning] Failed to parse ${configPath}:`, e);
    }
  }

  let gitCommit = "unknown";
  try {
    gitCommit = execSync("git rev-parse HEAD", { cwd: repoRoot, encoding: "utf-8" }).trim();
  } catch {
    // Fallback if git is unavailable (e.g. Docker container without git)
  }

  return {
    packageName: (config.packageName as string) ?? "boomtick",
    gitCommit,
    config,
  };
};

function tryParseJson(text: string): TDCliResponse | null {
  try {
    return JSON.parse(text) as TDCliResponse;
  } catch {
    return null;
  }
}

export async function runTDCli(args: string[]): Promise<TDCliResponse> {
  const result = await runCommand("td-cli", args);
  const stdout = result.stdout.trim();
  const output = stdout.startsWith("{") ? tryParseJson(stdout) : null;

  // Handle structured errors (status: "error") regardless of exit code
  if (output?.status === "error") {
    throw new Error(`td-cli returned error: ${output.message ?? "Unknown error"}`);
  }

  // Handle non-zero exit codes (shell failure)
  if (result.exitCode !== 0) {
    throw new Error(`td-cli command failed (${args.join(" ")}): ${result.stderr || stdout}`);
  }

  // Ensure we have a valid JSON response for successful exit
  if (!output) {
    throw new Error(`td-cli returned non-JSON output with exit code 0: ${stdout}`);
  }

  return output;
}
