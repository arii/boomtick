import { z } from "zod";
import { config } from "../config.js";
import { getTdPreflight } from "../lib/tdHealth.js";
import { getRagHealth } from "../lib/ragHealth.js";

export const HealthCheckInputSchema = z.object({
  checkDeep: z.boolean().optional().default(false),
});

export async function healthHandler(args: z.infer<typeof HealthCheckInputSchema>) {
  HealthCheckInputSchema.parse(args);
  return {
    status: "ok",
    config: {
      githubOwner: config.githubOwner,
      githubRepo: config.githubRepo,
      repoPath: config.repoPath,
      readOnly: !config.githubToken,
      ghPath: config.ghPath,
      // td availability recorded by the startup preflight; null when the
      // preflight has not run yet.
      tdAvailable: getTdPreflight()?.available ?? null,
      // Deterministic RAG index/canary state for this repo (silent 0-hit
      // indexes and never-built indexes surface here instead of being
      // diagnosed by hand).
      rag: getRagHealth(config.repoPath || process.cwd()),
    },
  };
}
