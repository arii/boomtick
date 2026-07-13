import { z } from "zod";
import { config } from "../config.js";

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
      ghPath: config.ghPath
    },
  };
}
