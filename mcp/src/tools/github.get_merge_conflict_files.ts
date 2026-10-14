import { z } from "zod";
import { getMergeConflictFiles } from "../lib/git.js";

export const GetMergeConflictFilesInputSchema = z.object({
  prNumber: z.number().optional(),
  baseBranch: z.string().optional().default("main"),
  headRef: z.string().optional().default("HEAD"),
});

export async function getMergeConflictFilesHandler(args: z.infer<typeof GetMergeConflictFilesInputSchema>) {
  const baseBranch = args.baseBranch || "main";
  const headRef = args.headRef || "HEAD";
  const conflictFiles = await getMergeConflictFiles(baseBranch, headRef);

  return {
    prNumber: args.prNumber,
    baseBranch,
    headRef,
    conflictFiles,
  };
}
