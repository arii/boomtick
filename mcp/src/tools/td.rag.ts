import { z } from "zod";
import { recordToolReceipt, resolveReceiptDir } from "../lib/session_manager.js";
import { runTDCli } from "../lib/tdCli.js";

export const TdRagInputSchema = z.object({
  repoRoot: z.string().optional().describe("Repo root for the RAG index (default: git root)."),
  query: z.string().describe("Natural-language query to run (no rebuild)."),
  topK: z.number().optional().describe("Maximum RAG hits to return."),
});

export async function tdRagHandler(args: z.infer<typeof TdRagInputSchema>) {
  const params = TdRagInputSchema.parse(args);
  const queryArgs = ["rag", "query", "--query", params.query];
  if (params.repoRoot) {
    queryArgs.push("--repo-root", params.repoRoot);
  }
  if (params.topK !== undefined) {
    queryArgs.push("--top-k", params.topK.toString());
  }
  queryArgs.push("--json");
  const rag = await runTDCli(queryArgs, "query RAG index");
  recordToolReceipt(resolveReceiptDir(params.repoRoot), "td.rag", {
    query: params.query,
  });
  return rag;
}
