import { spawn } from "child_process";
import { config } from "../config.js";
import path from "path";
import fs from "fs";

// Commands tools actually invoke: version control and td/gh entry
// points, plus the JS/Python test runners reachable via
// repo_run_tests. No shell builtins, no file destructive ops.
export const ALLOWED_COMMANDS = {
  git: "git",
  gh: "gh",
  td: "td",
  pnpm: "pnpm",
  npm: "npm",
  python3: "python3"
} as const;

export type AllowedCommand = keyof typeof ALLOWED_COMMANDS;

// Resolved td binary, computed once per process. The .venv probes
// hit the filesystem, so cache the winner instead of re-probing on
// every tool call.
let cachedTdPath: string | null = null;

export function resolveTdPath(): string {
  if (cachedTdPath !== null) {
    return cachedTdPath;
  }
  const candidates = [
    path.join(config.repoPath, ".venv", "bin", "td"),
    path.join(process.cwd(), ".venv", "bin", "td"),
    path.join(config.repoPath, "..", ".venv", "bin", "td"),
  ];
  for (const candidate of candidates) {
    let found = false;
    try {
      found = fs.existsSync(candidate);
    } catch {
      found = false;
    }
    if (found) {
      cachedTdPath = candidate;
      return cachedTdPath;
    }
  }
  cachedTdPath = "td";
  return cachedTdPath;
}

export function resetTdPathForTests(): void {
  cachedTdPath = null;
}

export interface ShellResult {
  stdout: string;
  stderr: string;
  exitCode: number | null;
  durationMs: number;
  command: string;
}

export async function runCommand(
  cmd: string,
  args: string[],
  options: { cwd?: string; timeout?: number; env?: Record<string, string> } = {}
): Promise<ShellResult> {
  if (!(cmd in ALLOWED_COMMANDS)) {
    throw new Error(`Command not allowed: ${cmd}`);
  }

  const safeCmd = cmd as AllowedCommand;

  const start = Date.now();
  const timeout = options.timeout || 60000;

  // Resolve path for 'gh' or 'td' if specified
  let finalCmd = ALLOWED_COMMANDS[safeCmd] as string;
  if (safeCmd === "gh") {
    finalCmd = config.ghPath;
  } else if (safeCmd === "td") {
    // In standalone mode, config.repoPath is the boomtick-pkg root.
    // The isolated .venv binary wins when present; resolved once per
    // process via resolveTdPath().
    finalCmd = resolveTdPath();
  }

  const env = {
    ...process.env,
    ...options.env,
    GH_TOKEN: config.githubToken,
    GITHUB_TOKEN: config.githubToken
  };

  return new Promise((resolve, reject) => {
    // nosemgrep
    const child = spawn(finalCmd, args, {
      cwd: options.cwd || config.repoPath,
      env
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    child.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    const timer = setTimeout(() => {
      child.kill();
      reject(new Error(`Command timed out: ${cmd} ${args.join(" ")}`));
    }, timeout);

    child.on("close", (code) => {
      clearTimeout(timer);
      const durationMs = Date.now() - start;

      // Redact token from output
      if (config.githubToken) {
        const redact = (str: string) => str.replace(new RegExp(config.githubToken!, "g"), "REDACTED");
        stdout = redact(stdout);
        stderr = redact(stderr);
      }

      resolve({
        stdout,
        stderr,
        exitCode: code,
        durationMs,
        command: `${cmd} ${args.join(" ")}`
      });
    });

    child.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}
