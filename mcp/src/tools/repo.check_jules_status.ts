import { z } from "zod";
import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";
import { config } from "../config.js";

export interface JulesStatusResult {
  sessionId: string;
  status: "COMPLETED" | "FAILED" | "IN_PROGRESS" | "TIMED_OUT" | "NOT_FOUND";
  rawState?: string;
  completed: boolean;
  remediationBranch?: string;
  pullRequestUrl?: string;
  idempotencyHash?: string;
  isDuplicate?: boolean;
  message?: string;
}

export const CheckJulesStatusInputSchema = z.object({
  sessionId: z.string().optional().describe("The unique ID or task ID of the Jules session."),
  commitSha: z.string().optional().describe("Commit SHA for idempotency key verification."),
  failureLog: z.string().optional().describe("Failure log content for idempotency key calculation."),
  poll: z.boolean().optional().describe("Whether to poll until session completion or timeout."),
  timeoutMs: z.number().int().optional().describe("Timeout in milliseconds when polling."),
  intervalMs: z.number().int().optional().describe("Polling interval in milliseconds."),
});

function calculateHash(commitSha: string, failureLog: string): string {
  const hash = crypto.createHash("sha256");
  return hash.update(`${commitSha}:${failureLog.trim()}`).digest("hex");
}

export async function checkJulesStatusHandler(input: z.infer<typeof CheckJulesStatusInputSchema>): Promise<JulesStatusResult> {
  let resolvedTaskId = input.sessionId || process.env.TASK_ID;

  if (!resolvedTaskId) {
    return {
      sessionId: "",
      status: "NOT_FOUND",
      completed: false,
      message: "No session ID provided.",
    };
  }

  const sessionId = resolvedTaskId.startsWith("sessions/") ? resolvedTaskId : `sessions/${resolvedTaskId}`;
  const apiKey = process.env.JULES_API_KEY;

  if (!apiKey) {
    return {
      sessionId,
      status: "NOT_FOUND",
      completed: false,
      message: "JULES_API_KEY environment variable not set.",
    };
  }

  const commitSha = input.commitSha || process.env.GITHUB_SHA || process.env.COMMIT_SHA;
  let idempotencyHash: string | undefined;
  let isDuplicate = false;

  if (commitSha && input.failureLog) {
    idempotencyHash = calculateHash(commitSha, input.failureLog);
    const artifactsDir = path.join(config.repoPath || process.cwd(), "artifacts");
    const hashTrackingFile = path.join(artifactsDir, `.jules-dispatch-${sessionId.replace(/[^a-zA-Z0-9_-]/g, "_")}.hash`);
    if (fs.existsSync(hashTrackingFile)) {
      try {
        const existingHash = fs.readFileSync(hashTrackingFile, "utf8").trim();
        if (existingHash === idempotencyHash) {
          isDuplicate = true;
        }
      } catch (e) {
        console.warn("⚠️ Could not read previous Jules dispatch hash file during status check:", e);
      }
    }
  }

  const url = `https://jules.googleapis.com/v1alpha/${sessionId}`;
  const poll = input.poll ?? false;
  const timeoutMs = input.timeoutMs ?? 60000;
  const intervalMs = input.intervalMs ?? 5000;
  const startTime = Date.now();

  const fetchSession = async () => {
    const response = await fetch(url, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        "x-goog-api-key": apiKey,
      },
    });
    if (!response.ok) {
      return null;
    }
    return await response.json();
  };

  while (true) {
    let sessionData: any = null;
    try {
      sessionData = await fetchSession();
    } catch (e) {
      console.warn(`⚠️ Error fetching Jules session status for ${sessionId}:`, e);
    }

    if (!sessionData) {
      return {
        sessionId,
        status: "NOT_FOUND",
        completed: false,
        idempotencyHash,
        isDuplicate,
        message: `Failed to retrieve session data for ${sessionId}`,
      };
    }

    const rawState = sessionData.state || "UNKNOWN";
    let status: JulesStatusResult["status"] = "IN_PROGRESS";
    if (rawState === "SUCCEEDED" || rawState === "COMPLETED") {
      status = "COMPLETED";
    } else if (rawState === "FAILED" || rawState === "CANCELLED" || rawState === "TERMINATED") {
      status = "FAILED";
    } else if (rawState === "IN_PROGRESS" || rawState === "PENDING") {
      status = "IN_PROGRESS";
    }

    let remediationBranch: string | undefined;
    let pullRequestUrl: string | undefined;

    if (sessionData.sourceContext?.githubRepoContext?.startingBranch) {
      remediationBranch = sessionData.sourceContext.githubRepoContext.startingBranch;
    }

    if (Array.isArray(sessionData.outputs)) {
      for (const output of sessionData.outputs) {
        if (output?.pullRequest?.url) {
          pullRequestUrl = output.pullRequest.url;
        }
        if (output?.pullRequest?.branch || output?.gitBranch) {
          remediationBranch = output?.pullRequest?.branch || output?.gitBranch;
        }
      }
    }

    const completed = status === "COMPLETED";

    if (!poll || status === "COMPLETED" || status === "FAILED") {
      return {
        sessionId,
        status,
        rawState,
        completed,
        remediationBranch,
        pullRequestUrl,
        idempotencyHash,
        isDuplicate,
        message: `Session state: ${rawState}`,
      };
    }

    if (Date.now() - startTime >= timeoutMs) {
      return {
        sessionId,
        status: "TIMED_OUT",
        rawState,
        completed: false,
        remediationBranch,
        pullRequestUrl,
        idempotencyHash,
        isDuplicate,
        message: `Polling timed out after ${timeoutMs}ms (current state: ${rawState})`,
      };
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}
