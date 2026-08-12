import { z } from "zod";
import { config } from "../config.js";
import { loadStandaloneAgentContext } from "../lib/td-cli.js";

export const ReadAgentContextInputSchema = z.object({});

export async function readAgentContextHandler(_args: z.infer<typeof ReadAgentContextInputSchema>) {
  const context = loadStandaloneAgentContext(config.repoPath);
  const result: any = {
    status: "success",
    ...context
  };
  delete result.submodules;
  if (result.config) {
    delete result.config.submodules;
  }
  return result;
}
