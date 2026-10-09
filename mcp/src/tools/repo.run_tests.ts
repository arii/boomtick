import { z } from "zod";
import { runCommand, ShellResult } from "../lib/shell.js";

export const RunTestsInputSchema = z.object({
  commands: z.array(z.string()).optional(),
  timeoutSeconds: z.number().optional().default(180),
  worktreePath: z.string().optional(),
});

/**
 * Safely parses a command string into [command, ...args], preserving quoted arguments.
 */
export function parseCommandString(fullCmd: string): [string, ...string[]] {
  const tokens: string[] = [];
  let currentToken = "";
  let inQuotes: boolean | string = false;

  for (let i = 0; i < fullCmd.length; i++) {
    const char = fullCmd[i];

    if (inQuotes) {
      if (char === inQuotes) {
        inQuotes = false;
      } else {
        currentToken += char;
      }
    } else {
      if (char === '"' || char === "'") {
        inQuotes = char;
      } else if (/\s/.test(char)) {
        if (currentToken.length > 0) {
          tokens.push(currentToken);
          currentToken = "";
        }
      } else {
        currentToken += char;
      }
    }
  }

  if (currentToken.length > 0) {
    tokens.push(currentToken);
  }

  if (tokens.length === 0) {
    return [""];
  }

  return [tokens[0], ...tokens.slice(1)] as [string, ...string[]];
}

export async function runTestsHandler(args: z.infer<typeof RunTestsInputSchema>) {
  const commands = args.commands || [
    "pnpm test"
  ];

  const results: ShellResult[] = [];
  let success = true;
  const timeoutMs = (args.timeoutSeconds || 180) * 1000;

  for (const fullCmd of commands) {
    const [cmd, ...cmdArgs] = parseCommandString(fullCmd);
    try {
      const res = await runCommand(cmd, cmdArgs, {
        cwd: args.worktreePath,
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

  return { success, results };
}
