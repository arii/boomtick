import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const RunPlaywrightInputSchema = z.object({
  grep: z.string().optional(),
  worktreePath: z.string().optional(),
});

export async function runPlaywrightHandler(args: z.infer<typeof RunPlaywrightInputSchema>) {
  const tdArgs = ["repo", "run-playwright"];
  if (args.grep) {
    tdArgs.push("--grep", args.grep);
  }
  if (args.worktreePath) {
    tdArgs.push("--worktree", args.worktreePath);
  }

  const result = await runCommand("td-cli", tdArgs);

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
