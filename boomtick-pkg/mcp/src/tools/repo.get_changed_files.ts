import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const GetChangedFilesInputSchema = z.object({
  base: z.string().optional().default("main"),
  head: z.string().optional().default("HEAD"),
});

export async function getChangedFilesHandler(args: z.infer<typeof GetChangedFilesInputSchema>) {
  const result = await runCommand("git", [
    "diff",
    "--name-status",
    `${args.base}...${args.head}`
  ]);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to get changed files: ${result.stderr}`);
  }

  const files = result.stdout.trim().split("\n").filter(line => line.length > 0).map(line => {
    const [status, path] = line.split(/\s+/);
    return { status, path };
  });

  return { files };
}
