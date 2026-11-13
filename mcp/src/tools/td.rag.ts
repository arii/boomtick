import { z } from "zod";
import { recordToolReceipt, resolveReceiptDir } from "../lib/session_manager.js";
import { runTDCli } from "../lib/tdCli.js";
import { TdRagInputSchema } from "./contract.js";

export { TdRagInputSchema };

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
