import * as fs from 'fs';
import * as path from 'path';
import * as crypto from 'crypto';
import { getJulesSessionIdFromPR } from './visualReviewUtils';

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

export async function checkJulesStatus(options: CheckJulesStatusOptions = {}): Promise<JulesStatusResult> {
  let resolvedTaskId = options.sessionId || process.env.TASK_ID;
  if (!resolvedTaskId) {
    resolvedTaskId = (await getJulesSessionIdFromPR()) || undefined;
  }

  if (!resolvedTaskId) {
    return {
      sessionId: '',
      status: 'NOT_FOUND',
      completed: false,
      message: 'No session ID provided or found in PR context.',
    };
  }

  const sessionId = resolvedTaskId.startsWith('sessions/') ? resolvedTaskId : `sessions/${resolvedTaskId}`;
  const apiKey = process.env.JULES_API_KEY;

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
    const artifactsDir = 'artifacts';
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

async function buildImpactReportBody(artifactsDir: string): Promise<string> {
  let body = '## Deployment Impact Analysis\n\n';

  const deploymentReviewPath = path.join(artifactsDir, 'deployment-review.md');
  const impactMdPath = path.join(artifactsDir, 'impact-analysis', 'impact.md');

  if (fs.existsSync(deploymentReviewPath)) {
    try {
      body += await fs.promises.readFile(deploymentReviewPath, 'utf8') + '\n\n';
    } catch (e) {
      console.error(`Failed to read ${deploymentReviewPath}:`, e);
    }
  } else if (fs.existsSync(impactMdPath)) {
    try {
      body += await fs.promises.readFile(impactMdPath, 'utf8') + '\n\n';
    } catch (e) {
      console.error(`Failed to read ${impactMdPath}:`, e);
    }
  } else {
    body += 'No impact report found.\n\n';
  }

  const reviewFiles = [
    'gemini-review.md',
    'github-models-review.md',
    'gemini-code-review.md',
    'github-models-code-review.md',
  ];

  const isSkippedReview = (content: string): boolean => {
    const lines = content.split('\n').map(l => l.trim()).filter(l => l.length > 0);
    return lines.length === 2 && lines[1].startsWith('Skipped:');
  };

  for (const filename of reviewFiles) {
    const filepath = path.join(artifactsDir, filename);
    if (fs.existsSync(filepath)) {
      try {
        const content = await fs.promises.readFile(filepath, 'utf8');
        if (!isSkippedReview(content)) {
          body += content + '\n\n';
        }
      } catch (e) {
        console.error(`Failed to read ${filepath}:`, e);
      }
    }
  }

  const searchDirs = ['.boomtick/logs/reviews', '.boomtick/logs/logs/reviews'];
  for (const searchDir of searchDirs) {
    if (fs.existsSync(searchDir)) {
      try {
        const files = await fs.promises.readdir(searchDir);
        for (const file of files) {
          if (file.startsWith('pr-review-') && file.endsWith('.md')) {
            const filepath = path.join(searchDir, file);
            const content = await fs.promises.readFile(filepath, 'utf8');
            if (!isSkippedReview(content)) {
              body += content + '\n\n';
            }
          }
        }
      } catch (e) {
        console.error(`Failed to read from ${searchDir}:`, e);
      }
    }
  }

  return body;
}

async function collectActionableVerdicts(artifactsDir: string): Promise<{
  verdicts: { fname: string; content: string }[];
  hasActionableReviews: boolean;
}> {
  const isSkippedVerdict = (data: any): boolean => {
    return (
      data?.llmVerdict === 'pass' &&
      data?.highCount === 0 &&
      (Array.isArray(data?.routes) ? data.routes.length === 0 : true) &&
      data?.passed === true
    );
  };

  const verdicts: { fname: string; content: string }[] = [];
  let hasActionableReviews = false;

  try {
    const files = await fs.promises.readdir(artifactsDir);
    for (const file of files) {
      if (file.endsWith('-verdict.json')) {
        const filepath = path.join(artifactsDir, file);
        try {
          const content = await fs.promises.readFile(filepath, 'utf8');
          const data = JSON.parse(content);
          if (!isSkippedVerdict(data)) {
            verdicts.push({ fname: file, content });

            const llmVerdict = data?.llmVerdict;
            const highCount = data?.highCount || 0;
            const passed = data?.passed ?? true;
            if (llmVerdict === 'fail' || llmVerdict === 'warn' || highCount > 0 || !passed) {
              hasActionableReviews = true;
            }
          }
        } catch (e) {
          console.error(`Failed to read/parse verdict file ${filepath}:`, e);
        }
      }
    }
  } catch (e) {
    console.error(`Failed to read artifacts directory:`, e);
  }

  return { verdicts, hasActionableReviews };
}

async function postJulesMessage(
  sessionId: string,
  apiKey: string,
  body: string,
  hashTrackingFile: string,
  dispatchHash: string
): Promise<void> {
  const url = `https://jules.googleapis.com/v1alpha/${sessionId}:sendMessage`;
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-goog-api-key': apiKey,
      },
      body: JSON.stringify({ prompt: body }),
    });

    if (!response.ok) {
      const text = await response.text();
      console.warn(`⚠️  Failed to send message to Jules API (non-blocking) (${response.status}): ${text}`);
      return;
    }

    console.log(`✅ Sent impact analysis to ${sessionId}`);
    try {
      await fs.promises.writeFile(hashTrackingFile, dispatchHash, 'utf8');
    } catch (e) {
      console.warn('⚠️ Could not record Jules dispatch hash file:', e);
    }
  } catch (error) {
    console.warn(`⚠️  Exception while sending message to Jules API (non-blocking):`, error);
  }
}

export async function sendJulesImpactReport(taskId?: string): Promise<void> {
  let resolvedTaskId = taskId || process.env.TASK_ID;
  if (!resolvedTaskId) {
    resolvedTaskId = (await getJulesSessionIdFromPR()) || undefined;
  }

  if (!resolvedTaskId) {
    console.log("No TASK_ID provided or found in PR description. Exiting.");
    return;
  }

  const sessionId = resolvedTaskId.startsWith('sessions/') ? resolvedTaskId : `sessions/${resolvedTaskId}`;
  console.log(`Targeting session: ${sessionId}`);

  const apiKey = process.env.JULES_API_KEY;
  if (!apiKey) {
    console.warn('⚠️  Skipping sending message to Jules session — JULES_API_KEY not set.');
    return;
  }

  const artifactsDir = 'artifacts';
  try {
    const stats = await fs.promises.stat(artifactsDir);
    if (!stats.isDirectory()) {
      console.warn(`Artifacts directory '${artifactsDir}' is not a directory. Cannot send impact analysis.`);
      return;
    }
  } catch (err) {
    console.warn(`Artifacts directory '${artifactsDir}' not found. Cannot send impact analysis.`);
    return;
  }

  let body = await buildImpactReportBody(artifactsDir);
  const { verdicts, hasActionableReviews } = await collectActionableVerdicts(artifactsDir);

  if (!hasActionableReviews) {
    console.log("No actionable issues/failures found in reviews. Skipping sending message to Jules.");
    return;
  }

  if (verdicts.length > 0) {
    body += "## Verdict JSONs\n";
    for (const { fname, content } of verdicts) {
      body += `### ${fname}\n\`\`\`json\n${content}\n\`\`\`\n\n`;
    }
  }

  const commitSha = process.env.GITHUB_SHA || process.env.COMMIT_SHA || 'unknown-sha';
  const dispatchHash = calculateJulesRemediationHash(commitSha, body);
  const hashTrackingFile = path.join(artifactsDir, `.jules-dispatch-${sessionId.replace(/[^a-zA-Z0-9_-]/g, '_')}.hash`);

  if (fs.existsSync(hashTrackingFile)) {
    try {
      const existingHash = (await fs.promises.readFile(hashTrackingFile, 'utf8')).trim();
      if (existingHash === dispatchHash) {
        console.log(`✨ Duplicate Jules dispatch skipped for session ${sessionId} (commit ${commitSha.slice(0, 7)} hash match).`);
        return;
      }
    } catch (e) {
      console.warn('⚠️ Could not read previous Jules dispatch hash file:', e);
    }
  }

  await postJulesMessage(sessionId, apiKey, body, hashTrackingFile, dispatchHash);
}
