import { z } from "zod";
import { runCommand, ShellResult } from "../lib/shell.js";

export const RunTestsInputSchema = z.object({
  commands: z.array(z.string()).optional(),
  timeoutSeconds: z.number().optional().default(300),
  worktreePath: z.string().optional(),
});

export async function runTestsHandler(args: z.infer<typeof RunTestsInputSchema>) {
  const commands = args.commands || [
    "pnpm install --frozen-lockfile",
    "pnpm lint",
    "pnpm test",
    "pnpm build"
  ];

  const results: ShellResult[] = [];
  let success = true;

  for (const fullCmd of commands) {
    const [cmd, ...cmdArgs] = fullCmd.split(" ");
    try {
      const res = await runCommand(cmd, cmdArgs, {
        cwd: args.worktreePath,
        timeout: args.timeoutSeconds * 1000
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
