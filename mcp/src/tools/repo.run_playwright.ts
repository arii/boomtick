import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const RunPlaywrightInputSchema = z.object({
  grep: z.string().optional(),
  worktreePath: z.string().optional(),
  timeoutSeconds: z.number().optional().default(180),
});

export type RunPlaywrightInput = z.input<typeof RunPlaywrightInputSchema>;

export async function runPlaywrightHandler(args: RunPlaywrightInput) {
  const parsed = RunPlaywrightInputSchema.parse(args || {});
  const tdArgs = ["repo", "run-playwright"];
  if (parsed.grep) {
    tdArgs.push("--grep", parsed.grep);
  }
  if (parsed.worktreePath) {
    tdArgs.push("--worktree", parsed.worktreePath);
  }

  const result = await runCommand("td-cli", tdArgs, {
    cwd: parsed.worktreePath,
    timeout: parsed.timeoutSeconds * 1000,
  });

  if (result.exitCode !== 0) {
    // Playwright might exit with non-zero if tests fail, but our td-cli should ideally handle it
    // and return a JSON with success: false.
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
     throw new Error(`Failed to run Playwright: ${output.message}`);
  }

  return {
    success: output.success,
    command: output.command,
    failedTests: output.failedTests
  };
}
