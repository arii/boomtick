import { z } from "zod";
import { recordToolReceipt } from "../lib/session_manager.js";
import { runTDCli } from "../lib/tdCli.js";

export const TdInitAndRagInputSchema = z.object({
  repoRoot: z.string().optional().describe("Repo root to initialize (default: git root)."),
  query: z.string().optional().describe("Optional natural-language query to run after init."),
  topK: z.number().optional().describe("Maximum RAG hits to return."),
});

export async function tdInitAndRagHandler(args: z.infer<typeof TdInitAndRagInputSchema>) {
  const params = TdInitAndRagInputSchema.parse(args);
  const initArgs = ["init"];
  if (params.repoRoot) {
    initArgs.push("--repo-root", params.repoRoot);
  }
  initArgs.push("--json");
  const init = await runTDCli(initArgs, "initialize repo");

  if (!params.query) {
    recordToolReceipt(params.repoRoot ?? process.cwd(), "td.init_and_rag");
    return init;
  }
  const queryArgs = ["rag", "query", "--query", params.query];
  if (params.repoRoot) {
    queryArgs.push("--repo-root", params.repoRoot);
  }
  if (params.topK !== undefined) {
    queryArgs.push("--top-k", params.topK.toString());
  }
  queryArgs.push("--json");
  const rag = await runTDCli(queryArgs, "query RAG index");
  recordToolReceipt(params.repoRoot ?? process.cwd(), "td.init_and_rag", {
    query: params.query,
  });
  return { init, rag };
}
