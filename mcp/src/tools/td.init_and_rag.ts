import { z } from "zod";
import { recordToolReceipt } from "../lib/session_manager.js";
import { emitToolTelemetry } from "../lib/tool_telemetry.js";
import { runTDCli } from "../lib/tdCli.js";

/** @deprecated Prefer td_init + td_rag so queries skip rebuilds (#1139 item 2). */
export const TdInitAndRagInputSchema = z.object({
  repoRoot: z.string().optional().describe("Repo root to initialize (default: git root)."),
  query: z.string().optional().describe("Optional natural-language query to run after init."),
  topK: z.number().optional().describe("Maximum RAG hits to return."),
});

export async function tdInitAndRagHandler(args: z.infer<typeof TdInitAndRagInputSchema>) {
  const params = TdInitAndRagInputSchema.parse(args);
  const cwd = params.repoRoot ?? process.cwd();
  const started = Date.now();
  // Session locus must be explicit: without repoRoot the line would
  // land in the server cwd as stray clutter (issue #1157).
  const done = (ok: boolean, detail?: string) => {
    if (params.repoRoot) {
      emitToolTelemetry(cwd, "td.init_and_rag", ok, Date.now() - started, detail);
    }
  };
  const initArgs = ["init"];
  if (params.repoRoot) {
    initArgs.push("--repo-root", params.repoRoot);
  }
  initArgs.push("--json");
  let init;
  try {
    init = await runTDCli(initArgs, "initialize repo");
  } catch (err) {
    done(false, err instanceof Error ? err.message : String(err));
    throw err;
  }

  if (!params.query) {
    recordToolReceipt(cwd, "td.init_and_rag");
    done(true);
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
  let rag;
  try {
    rag = await runTDCli(queryArgs, "query RAG index");
  } catch (err) {
    done(false, err instanceof Error ? err.message : String(err));
    throw err;
  }
  recordToolReceipt(cwd, "td.init_and_rag", {
    query: params.query,
  });
  done(true);
  return { init, rag };
}
