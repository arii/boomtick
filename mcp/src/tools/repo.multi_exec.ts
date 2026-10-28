import { z } from "zod";
import { runTDCli } from "./jules/shared.js";

export const MultiExecInputSchema = z.object({
  command: z.string().describe("Shell command to execute sequentially across repositories"),
  repos: z.array(z.string()).optional().describe("Optional list of repository names to target"),
  continueOnError: z.boolean().optional().default(true).describe("Whether to continue execution if a repo command fails"),
});

export async function multiExecHandler(input: z.input<typeof MultiExecInputSchema>) {
  const args = MultiExecInputSchema.parse(input);
  const cliArgs = ["multi-repo", "exec", args.command];
  if (args.repos) {
    for (const r of args.repos) {
      cliArgs.push("-r", r);
    }
  }
  if (args.continueOnError === false) {
    cliArgs.push("--fail-fast");
  }
  const output = await runTDCli(cliArgs, "execute command across ecosystem repositories");
  return output;
}
