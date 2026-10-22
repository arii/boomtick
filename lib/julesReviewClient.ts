import * as fs from 'fs';
import * as path from 'path';
import * as crypto from 'crypto';
import { getJulesSessionIdFromPR } from './visualReviewUtils';

export function calculateJulesRemediationHash(commitSha: string, bodyContent: string): string {
  const hash = crypto.createHash('sha256');
  return hash.update(`${commitSha}:${bodyContent.trim()}`).digest('hex');
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

  let hasActionableReviews = false;

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

  const isSkippedVerdict = (data: any): boolean => {
    return (
      data?.llmVerdict === 'pass' &&
      data?.highCount === 0 &&
      (Array.isArray(data?.routes) ? data.routes.length === 0 : true) &&
      data?.passed === true
    );
  };

  const verdicts: { fname: string; content: string }[] = [];

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
