import { z } from "zod";
import { getChangedFiles, resolveRepoPath } from "../lib/git.js";

export const GetChangedFilesInputSchema = z.object({
  base: z.string().optional().default("main"),
  head: z.string().optional().default("HEAD"),
  repo: z.string().optional().describe("Target GitHub repository override."),
  path: z.string().optional().describe("Local filesystem path to target repository root."),
  repoPath: z.string().optional().describe("Alias for path to target repository root."),
});

export async function getChangedFilesHandler(args: z.infer<typeof GetChangedFilesInputSchema>) {
  const targetCwd = resolveRepoPath({
    path: args.path,
    repoPath: args.repoPath,
    repo: args.repo,
  });
  const files = await getChangedFiles(args.base || "main", args.head || "HEAD", targetCwd);
  return { files };
}
