import * as fs from 'fs';
import * as path from 'path';
import * as crypto from 'crypto';

export interface CheckJulesStatusOptions {
  sessionId?: string;
  commitSha?: string;
  failureLog?: string;
  poll?: boolean;
  timeoutMs?: number;
  intervalMs?: number;
}

export interface JulesStatusResult {
  sessionId: string;
  status: 'COMPLETED' | 'FAILED' | 'IN_PROGRESS' | 'TIMED_OUT' | 'NOT_FOUND';
  rawState?: string;
  completed: boolean;
  remediationBranch?: string;
  pullRequestUrl?: string;
  idempotencyHash?: string;
  isDuplicate?: boolean;
  message?: string;
}

export function calculateJulesRemediationHash(commitSha: string, bodyContent: string): string {
  const hash = crypto.createHash('sha256');
  return hash.update(`${commitSha}:${bodyContent.trim()}`).digest('hex');
}

export async function pollJulesStatus(
  resolvedTaskId: string | undefined,
  apiKey: string | undefined,
  artifactsDir: string,
  options: CheckJulesStatusOptions
): Promise<JulesStatusResult> {
  if (!resolvedTaskId) {
    return {
      sessionId: '',
      status: 'NOT_FOUND',
      completed: false,
      message: 'No session ID provided or found in PR context.',
    };
  }

  const sessionId = resolvedTaskId.startsWith('sessions/') ? resolvedTaskId : `sessions/${resolvedTaskId}`;

  if (!apiKey) {
    return {
      sessionId,
      status: 'NOT_FOUND',
      completed: false,
      message: 'JULES_API_KEY environment variable not set.',
    };
  }

  const commitSha = options.commitSha || process.env.GITHUB_SHA || process.env.COMMIT_SHA;
  let idempotencyHash: string | undefined;
  let isDuplicate = false;

  if (commitSha && options.failureLog) {
    idempotencyHash = calculateJulesRemediationHash(commitSha, options.failureLog);
    const hashTrackingFile = path.join(artifactsDir, `.jules-dispatch-${sessionId.replace(/[^a-zA-Z0-9_-]/g, '_')}.hash`);
    if (fs.existsSync(hashTrackingFile)) {
      try {
        const existingHash = (await fs.promises.readFile(hashTrackingFile, 'utf8')).trim();
        if (existingHash === idempotencyHash) {
          isDuplicate = true;
        }
      } catch (e) {
        console.warn('⚠️ Could not read previous Jules dispatch hash file during status check:', e);
      }
    }
  }

  const url = `https://jules.googleapis.com/v1alpha/${sessionId}`;
  const poll = options.poll ?? false;
  const timeoutMs = options.timeoutMs ?? 60000;
  const intervalMs = options.intervalMs ?? 5000;
  const startTime = Date.now();

  const fetchSession = async () => {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'x-goog-api-key': apiKey,
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
        status: 'NOT_FOUND',
        completed: false,
        idempotencyHash,
        isDuplicate,
        message: `Failed to retrieve session data for ${sessionId}`,
      };
    }

    const rawState = sessionData.state || 'UNKNOWN';
    let status: JulesStatusResult['status'] = 'IN_PROGRESS';
    if (rawState === 'SUCCEEDED' || rawState === 'COMPLETED') {
      status = 'COMPLETED';
    } else if (rawState === 'FAILED' || rawState === 'CANCELLED' || rawState === 'TERMINATED') {
      status = 'FAILED';
    } else if (rawState === 'IN_PROGRESS' || rawState === 'PENDING') {
      status = 'IN_PROGRESS';
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

    const completed = status === 'COMPLETED';

    if (!poll || status === 'COMPLETED' || status === 'FAILED') {
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
        status: 'TIMED_OUT',
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
