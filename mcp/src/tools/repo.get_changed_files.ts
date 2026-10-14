import { z } from "zod";
import { getChangedFiles } from "../lib/git.js";

export const GetChangedFilesInputSchema = z.object({
  base: z.string().optional().default("main"),
  head: z.string().optional().default("HEAD"),
});

export async function getChangedFilesHandler(args: z.infer<typeof GetChangedFilesInputSchema>) {
  const files = await getChangedFiles(args.base || "main", args.head || "HEAD");
  return { files };
}
