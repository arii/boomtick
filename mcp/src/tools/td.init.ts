import { z } from "zod";
import { recordToolReceipt, resolveReceiptDir } from "../lib/session_manager.js";
import { runTDCli } from "../lib/tdCli.js";
import { TdInitInputSchema } from "./contract.js";

export { TdInitInputSchema };

export async function tdInitHandler(args: z.infer<typeof TdInitInputSchema>) {
  const params = TdInitInputSchema.parse(args);
  const initArgs = ["init"];
  if (params.repoRoot) {
    initArgs.push("--repo-root", params.repoRoot);
  }
  initArgs.push("--json");
  const init = await runTDCli(initArgs, "initialize repo");
  recordToolReceipt(resolveReceiptDir(params.repoRoot), "td.init");
  return init;
}
