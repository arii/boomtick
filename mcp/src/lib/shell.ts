import { spawn } from "child_process";
import { config } from "../config.js";
import path from "path";
import fs from "fs";

export const ALLOWED_COMMANDS = {
  git: "git",
  gh: "gh",
  td: "td",
  "td-cli": "td-cli",
  pnpm: "pnpm",
  ls: "ls",
  rm: "rm",
  mkdir: "mkdir",
  cp: "cp",
  python3: "python3"
} as const;

export type AllowedCommand = keyof typeof ALLOWED_COMMANDS;

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

  // Resolve path for 'gh', 'td', or 'td-cli' if specified
  let finalCmd = ALLOWED_COMMANDS[safeCmd] as string;
  if (safeCmd === "gh") {
    finalCmd = config.ghPath;
  } else if (safeCmd === "td" || safeCmd === "td-cli") {
    // Check common venv locations for 'td' first, then 'td-cli'
    const resolveCliPath = (binName: string): string | null => {
      const venvBin = path.join(config.repoPath, ".venv", "bin", binName);
      const localVenvBin = path.join(process.cwd(), ".venv", "bin", binName);
      const parentVenvBin = path.join(config.repoPath, "..", ".venv", "bin", binName);

      if (fs.existsSync(venvBin)) return venvBin;
      if (fs.existsSync(localVenvBin)) return localVenvBin;
      if (fs.existsSync(parentVenvBin)) return parentVenvBin;
      return null;
    };

    const resolvedTd = resolveCliPath("td");
    const resolvedTdCli = resolveCliPath("td-cli");

    if (resolvedTd) {
      finalCmd = resolvedTd;
    } else if (resolvedTdCli) {
      finalCmd = resolvedTdCli;
    } else {
      // If safeCmd was 'td-cli' or 'td', default to requested command or fallback
      finalCmd = safeCmd;
    }
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
