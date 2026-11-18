import { z } from "zod";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { runCommand, ShellResult } from "../lib/shell.js";
import { RepoTestInputSchema } from "./contract.js";

export { RepoTestInputSchema };

function parseCommandArguments(fullCmd: string): [string, string[]] {
  const tokens: string[] = [];
  const regex = /"([^"\\]*(?:\\.[^"\\]*)*)"|'([^'\\]*(?:\\.[^'\\]*)*)'|(\S+)/g;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(fullCmd)) !== null) {
    if (match[1] !== undefined) {
      tokens.push(match[1].replace(/\\"/g, '"'));
    } else if (match[2] !== undefined) {
      tokens.push(match[2].replace(/\\'/g, "'"));
    } else {
      tokens.push(match[3]);
    }
  }
  if (tokens.length === 0) {
    return ["", []];
  }
  const [cmd, ...args] = tokens;
  return [cmd, args];
}

export async function repoTestHandler(args: z.input<typeof RepoTestInputSchema>) {
  const parsed = RepoTestInputSchema.parse(args ?? {});
  let commands = parsed.commands;
  if (!commands) {
    const packageJsonPath = path.join(parsed.worktreePath ?? process.cwd(), "package.json");
    const pkg = JSON.parse(await readFile(packageJsonPath, "utf-8"));
    commands = [
      "pnpm install --frozen-lockfile",
      ...["lint", "test", "build"]
        .filter((script) => Object.hasOwn(pkg.scripts ?? {}, script))
        .map((script) => `pnpm ${script}`)
    ];
  }
  const timeoutMs = (parsed.timeoutSeconds ?? 300) * 1000;

  const results: ShellResult[] = [];
  let success = true;

  for (const fullCmd of commands) {
    const [cmd, cmdArgs] = parseCommandArguments(fullCmd);
    try {
      const res = await runCommand(cmd, cmdArgs, {
        cwd: parsed.worktreePath ?? undefined,
        timeout: timeoutMs
      });
      results.push(res);
      if (res.exitCode !== 0) {
        success = false;
        break;
      }
    } catch (e) {
      success = false;
      results.push({
        command: fullCmd,
        stdout: "",
        stderr: e instanceof Error ? e.message : String(e),
        exitCode: 1,
        durationMs: 0
      });
      break;
    }
  }

  const exitCode = results.length > 0 ? results[results.length - 1].exitCode : 0;
  const failedTests: string[] = [];
  for (const res of results) {
    if (res.exitCode !== 0) {
      failedTests.push(res.command);
    }
  }

  return {
    passed: success,
    exitCode,
    failedTests,
    results,
  };
}
