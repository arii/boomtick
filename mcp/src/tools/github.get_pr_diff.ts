import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const GetPrDiffInputSchema = z.object({
  prNumber: z.number(),
});

export async function getPrDiffHandler(args: z.infer<typeof GetPrDiffInputSchema>) {
  const result = await runCommand("td-cli", [
    "gh", "pr-diff", args.prNumber.toString()
  ]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to get PR diff: ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to get PR diff: ${output.message}`);
  }

  // Every TypeScript tool file must be a pure routing shim
  return {
    prNumber: output.prNumber,
    files: output.files,
    diffText: output.diffText,
    truncated: output.truncated
  };
}
