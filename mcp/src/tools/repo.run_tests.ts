import { z } from "zod";
import { runCommand, ShellResult } from "../lib/shell.js";

export const RunTestsInputSchema = z.object({
  commands: z.array(z.string()).optional(),
  timeoutSeconds: z.number().optional().default(300),
  worktreePath: z.string().optional(),
});

export type RunTestsInput = z.input<typeof RunTestsInputSchema>;

export function parseCommandArguments(fullCmd: string): [string, string[]] {
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

export async function runTestsHandler(args: RunTestsInput) {
  const parsed = RunTestsInputSchema.parse(args || {});
  const commands = parsed.commands || [
    "pnpm install --frozen-lockfile",
    "pnpm lint",
    "pnpm test",
    "pnpm build"
  ];

  const results: ShellResult[] = [];
  let success = true;

  for (const fullCmd of commands) {
    const [cmd, cmdArgs] = parseCommandArguments(fullCmd);
    try {
      const res = await runCommand(cmd, cmdArgs, {
        cwd: parsed.worktreePath,
        timeout: parsed.timeoutSeconds * 1000
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
