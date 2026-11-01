import { z } from "zod";
import * as path from "path";
import { config } from "../config.js";
import {
  CheckJulesStatusOptions,
  JulesStatusResult,
  pollJulesStatus
} from "../lib/julesStatusUtils.js";

export const CheckJulesStatusInputSchema = z.object({
  sessionId: z.string().optional().describe("The unique ID or task ID of the Jules session."),
  commitSha: z.string().optional().describe("Commit SHA for idempotency key verification."),
  failureLog: z.string().optional().describe("Failure log content for idempotency key calculation."),
  poll: z.boolean().optional().describe("Whether to poll until session completion or timeout."),
  timeoutMs: z.number().int().optional().describe("Timeout in milliseconds when polling."),
  intervalMs: z.number().int().optional().describe("Polling interval in milliseconds."),
});

export async function checkJulesStatusHandler(input: z.infer<typeof CheckJulesStatusInputSchema>): Promise<JulesStatusResult> {
  const resolvedTaskId = input.sessionId || process.env.TASK_ID;
  const apiKey = process.env.JULES_API_KEY;
  const artifactsDir = path.join(config.repoPath || process.cwd(), "artifacts");

  return pollJulesStatus(resolvedTaskId, apiKey, artifactsDir, {
    commitSha: input.commitSha,
    failureLog: input.failureLog,
    poll: input.poll,
    timeoutMs: input.timeoutMs,
    intervalMs: input.intervalMs,
  });
}
