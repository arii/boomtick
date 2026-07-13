import { z } from "zod";
import fs from "fs/promises";
import path from "path";
import { config } from "../config.js";

export const ReadAgentContextInputSchema = z.object({});

export async function readAgentContextHandler(_args: z.infer<typeof ReadAgentContextInputSchema>) {
  const contextPath = path.join(config.repoPath, ".agent-context.json");

  try {
    const content = await fs.readFile(contextPath, "utf-8");
    const parsed = JSON.parse(content);
    return {
      status: "success",
      ...parsed
    };
  } catch (e: any) {
    console.error("Failed to read agent context:", e.message);
    throw new Error(`Failed to read agent context from ${contextPath}. Ensure it exists by running 'td-cli context-warm'.`);
  }
}
