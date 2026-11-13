import { z } from "zod";
import { config } from "../config.js";
import { getTdPreflight } from "../lib/tdHealth.js";

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
      tdAvailable: getTdPreflight()?.available ?? null
    },
  };
}
