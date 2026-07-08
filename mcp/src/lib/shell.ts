import { spawn } from "child_process";
import { config } from "../config.js";
import path from "path";

export const ALLOWED_COMMANDS = {
  git: "git",
  gh: "gh",
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

  // Resolve path for 'gh' if specified
  let finalCmd = ALLOWED_COMMANDS[safeCmd] as string;
  if (safeCmd === "gh") {
    finalCmd = config.ghPath;
  }

  const cliPath = path.join(config.repoPath, "boomtick-pkg/cli");
  const env = {
    ...process.env,
    ...options.env,
    PYTHONPATH: process.env.PYTHONPATH
      ? `${cliPath}:${process.env.PYTHONPATH}`
      : cliPath,
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
