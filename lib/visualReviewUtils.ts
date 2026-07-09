import * as fs from 'fs';
import * as path from 'path';
import { Buffer } from 'node:buffer';
import type { RouteReview, VisualRouteSummary, VisualReviewFinding, VisualReviewState } from './visualReviewTypes';
import { DOM_REVIEW_DIR, REVIEW_PROMPT } from './visualReviewConstants';

export function parseVisualReviewFindings(feedback: string): VisualReviewFinding[] {
  const openTag = '<findings>';
  const closeTag = '</findings>';

  const openIdx = feedback.lastIndexOf(openTag);
  const closeIdx = feedback.lastIndexOf(closeTag);

  if (openIdx === -1 || closeIdx === -1 || closeIdx < openIdx) {
    const openedButNeverClosed = openIdx !== -1 && (closeIdx === -1 || closeIdx < openIdx);
    if (openedButNeverClosed) {
      console.warn('⚠️ Visual findings block opened but never closed (truncation?).');
    }
    return [];
  }

  let jsonText = feedback.slice(openIdx + openTag.length, closeIdx).trim();

  const startIdx = jsonText.indexOf('{');
  const endIdx = jsonText.lastIndexOf('}');
  if (startIdx !== -1 && endIdx !== -1 && endIdx >= startIdx) {
    jsonText = jsonText.slice(startIdx, endIdx + 1);
  } else {
    jsonText = jsonText.replace(/^```[a-z]*\s*/gi, '').replace(/\s*```$/g, '').trim();
  }

  try {
    const data = JSON.parse(jsonText) as VisualReviewState;
    if (data.findings && Array.isArray(data.findings)) {
      data.findings = data.findings.map(f => {
        if (f && typeof f === 'object' && typeof f.status === 'string') {
          return { ...f, status: f.status.toLowerCase() as 'open' | 'resolved' };
        }
        return f;
      });
    }
    return data.findings || [];
  } catch (e) {
    console.warn('Failed to parse findings JSON from visual LLM response:', e);
    return [];
  }
}

export function imageToBase64(filePath: string): string {
  return fs.readFileSync(filePath).toString('base64');
}

export function parseLLMVerdict(feedback: string): 'pass' | 'fail' | 'warn' {
  // 1. Split feedback to isolate the main evaluation from recommendations and structured state
  const parts = feedback.split(/recommendations for improvement|---|<findings>/i);
  const coreEvaluation = parts[0] || '';

  // 2. Clean the core evaluation of "resolved" findings to avoid false failure signals
  const lines = coreEvaluation.split('\n');
  const activeLines = lines.filter(line => {
    const isResolved = /status["']?\s*:\s*["']?resolved["']?/i.test(line) ||
                       /✅|resolved|fixed/i.test(line);

    // Filter out positive affirmations to avoid false positives on negative keywords (e.g. "no clipping")
    const isPositiveAffirmation = /none found|no new issues|no regression|consistent|no evidence of|intentional|visually stable|preserved|no clipping|no overflow|no issues|no major|no significant/i.test(line);

    return !isResolved && !isPositiveAffirmation;
  });

  const activeText = activeLines.join('\n').toLowerCase();

  // 3. Look for explicit failure signals in the remaining "active" text
  if (/❌|bug|regression|broken|clipping|overflow|missing|unintentional/i.test(activeText)) return 'fail';

  // 4. Check for warnings, but only in the core evaluation.
  // We ignore polish recommendations from triggering a CI-blocking 'warn' verdict on HIGH severity routes.
  if (/⚠️|warn|minor|unbalanced/i.test(activeText)) return 'warn';

  return 'pass';
}

export function severityEmoji(severity: 'LOW' | 'MEDIUM' | 'HIGH'): string {
  if (severity === 'HIGH') return '🔴';
  if (severity === 'MEDIUM') return '🟡';
  return '🟢';
}

export function buildVisualReviewPayload(summary: VisualRouteSummary): Array<{ type: 'text'; text: string } | { type: 'image_url'; image_url: { url: string } }> {
  const beforePath = summary.beforePath;
  const afterPath = summary.afterPath;
  const diffPath = summary.diffPath;

  // 1. Grab the DOM diff for ground truth
  const routeDomDir = path.join(DOM_REVIEW_DIR, summary.slug);
  const domDiffPath = path.join(routeDomDir, 'diff.txt');
  let domDiffContext = 'No DOM diff available.';
  if (fs.existsSync(domDiffPath)) {
    const diffContent = fs.readFileSync(domDiffPath, 'utf8');
    domDiffContext = diffContent.length > 3000
      ? diffContent.slice(0, 3000) + '\n...[TRUNCATED]'
      : diffContent;
  }

  // 2. Grab the DOM structure diff
  const structureDiffPath = path.join(routeDomDir, 'structure-diff.txt');
  let structureDiffContext = 'No DOM structure diff available.';
  if (fs.existsSync(structureDiffPath)) {
    const diffContent = fs.readFileSync(structureDiffPath, 'utf8');
    structureDiffContext = diffContent.length > 2000
      ? diffContent.slice(0, 2000) + '\n...[TRUNCATED]'
      : diffContent;
  }

  // 3. Build the payload
  const baseContent: Array<{ type: 'text'; text: string } | { type: 'image_url'; image_url: { url: string } }> = [
    { type: 'text', text: REVIEW_PROMPT },
    { type: 'text', text: `Route: ${summary.route} | Pixel difference: ${summary.differencePercent.toFixed(2)}% | Severity: ${summary.severity}` },
  ];

  if (summary.validation && !summary.validation.passed) {
    baseContent.push({
      type: 'text',
      text: `AUTOMATED LAYOUT FAILURE: ${summary.validation.reason}`
    });
  }

  if (summary.metrics) {
    baseContent.push({
      type: 'text',
      text: `LAYOUT METRICS:
Base: Width=${summary.metrics.before.scrollWidth}px, Main=${summary.metrics.before.mainWidth}px, Height=${summary.metrics.before.scrollHeight}px
PR: Width=${summary.metrics.after.scrollWidth}px, Main=${summary.metrics.after.mainWidth}px, Height=${summary.metrics.after.scrollHeight}px
Viewport: ${summary.metrics.after.viewportWidth}px`
    });
  }

  baseContent.push(
    { type: 'text', text: `DOM STRUCTURE DIFF:\n\n${structureDiffContext}` },
    { type: 'text', text: `DOM TEXT DIFF:\n\n${domDiffContext}` },
    { type: 'text', text: 'BEFORE' },
    { type: 'image_url', image_url: { url: `data:image/png;base64,${imageToBase64(beforePath)}` } },
    { type: 'text', text: 'AFTER' },
    { type: 'image_url', image_url: { url: `data:image/png;base64,${imageToBase64(afterPath)}` } },
  );

  if (diffPath && fs.existsSync(diffPath)) {
    baseContent.push(
      { type: 'text', text: 'VISUAL DIFF' },
      { type: 'image_url', image_url: { url: `data:image/png;base64,${imageToBase64(diffPath)}` } }
    );
  }

  return baseContent;
}

export function generateMarkdownReport(
  reviews: RouteReview[],
  botName: string,
  reportTitle: string,
  botTagline: string
): string {
  const highCount = reviews.filter(r => r.severity === 'HIGH').length;
  const medCount = reviews.filter(r => r.severity === 'MEDIUM').length;
  const lowCount = reviews.filter(r => r.severity === 'LOW').length;

  const totalCost = reviews.reduce((acc, r) => acc + r.cost, 0);
  const totalTokens = reviews.reduce((acc, r) => acc + r.tokens, 0);

  const prNumber = process.env.PR_NUMBER;
  const prLink = prNumber ? `[PR #${prNumber}](https://github.com/${process.env.GITHUB_REPOSITORY}/pull/${prNumber})` : 'this PR';

  const sections = reviews.map(r => `
### ${severityEmoji(r.severity)} \`${r.route}\` ${r.role ? `(${r.role})` : ''}

**Pixel diff:** ${r.differencePercent.toFixed(2)}%

${r.feedback}
`).join('\n---\n');

  let costLine = '';
  if (totalCost > 0) {
    costLine = `**Cost:** ~$${totalCost.toFixed(5)} (${totalTokens} tokens)\n`;
  }

  const modelLine = reviews[0]?.modelName ? `**Model:** ${reviews[0].modelName}\n` : '';

  return `## ${reportTitle}

> ${botTagline}

**Summary:** 🔴 ${highCount} high · 🟡 ${medCount} medium · 🟢 ${lowCount} low
**Reviewing:** ${prLink}
${costLine}
${modelLine}
${sections}

---
*Generated by ${botName} — [Blast-Radius Analyzer](https://boomtick.blog/research)*
`;
}

export async function getJulesSessionIdFromPR(): Promise<string | null> {
  const token = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPOSITORY;
  const prNumber = process.env.PR_NUMBER;

  if (!token || !repo || !prNumber) return null;

  const url = `https://api.github.com/repos/${repo}/pulls/${prNumber}`;
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' },
  });

  if (!response.ok) return null;

  const prData = await response.json() as { body: string | null };
  if (!prData.body) return null;

  const match = prData.body.match(/jules\.google\.com\/task\/([0-9]+)/);
  return match ? match[1] : null;
}

export async function sendJulesMessage(taskId: string, message: string): Promise<void> {
  const apiKey = process.env.JULES_API_KEY;
  if (!apiKey) {
    console.warn('⚠️  Skipping sending message to Jules session — JULES_API_KEY not set.');
    return;
  }

  const url = `https://jules.googleapis.com/v1alpha/sessions/${taskId}:sendMessage`;
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-goog-api-key': apiKey,
      },
      body: JSON.stringify({ prompt: message }),
    });

    if (!response.ok) {
      const text = await response.text();
      console.warn(`⚠️  Failed to send message to Jules API (${response.status}): ${text}`);
      return;
    }

    console.log(`✅ Sent message to Jules session ${taskId}`);
  } catch (error) {
    console.warn(`⚠️  Error sending message to Jules API:`, error);
  }
}

export async function countExistingReviews(reportTitles: string[]): Promise<number> {
  const token = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPOSITORY;
  const prNumber = process.env.PR_NUMBER;

  if (!token || !repo || !prNumber) return 0;

  const url = `https://api.github.com/repos/${repo}/issues/${prNumber}/comments`;
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' },
  });

  if (!response.ok) return 0;

  const comments = await response.json() as Array<{ body: string; user: { type: string } }>;
  let totalReviews = 0;
  for (const c of comments) {
    if (c.user.type === 'Bot' && reportTitles.some(title => c.body.includes(`## ${title}`))) {
      const match = c.body.match(/<!-- ai-review-count: (\d+) -->/);
      if (match) {
        totalReviews += parseInt(match[1], 10);
      } else {
        totalReviews += 1;
      }
    }
  }
  return totalReviews;
}

export async function getPreviousReviewState<T>(reportTitle: string): Promise<T | undefined> {
  const token = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPOSITORY;
  const prNumber = process.env.PR_NUMBER;

  if (!token || !repo || !prNumber) return undefined;

  let url: string | null = `https://api.github.com/repos/${repo}/issues/${prNumber}/comments?per_page=100`;
  let existingComment: { body: string; user: { type: string } } | undefined;

  while (url) {
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' },
    });

    if (!response.ok) return undefined;

    const comments = await response.json() as Array<{ body: string; user: { type: string } }>;
    existingComment = comments.find(c =>
      c.user.type === 'Bot' && c.body.includes(`## ${reportTitle}`)
    );

    if (existingComment) break;

    // Handle pagination
    const linkHeader = response.headers.get('Link');
    const nextMatch = linkHeader?.match(/<([^>]+)>;\s*rel="next"/);
    url = nextMatch ? nextMatch[1] : null;
  }

  if (!existingComment) return undefined;

  const stateMatch = existingComment.body.match(/<!-- ai-review-state: (.*?) -->/);
  if (!stateMatch) return undefined;

  try {
    const base64 = stateMatch[1];
    return JSON.parse(Buffer.from(base64, 'base64').toString('utf-8')) as T;
  } catch (e) {
    console.warn('Failed to parse previous review state:', e);
    return undefined;
  }
}

export async function postPRComment(body: string, reportTitle: string, state?: unknown): Promise<void> {
  const token = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPOSITORY;
  const prNumber = process.env.PR_NUMBER;

  if (!token || !repo || !prNumber) {
    console.warn('⚠️  Skipping PR comment — GITHUB_TOKEN, GITHUB_REPOSITORY, or PR_NUMBER not set.');
    return;
  }

  const url = `https://api.github.com/repos/${repo}/issues/${prNumber}/comments`;

  let stateTag = '';
  if (state) {
    try {
      stateTag = `<!-- ai-review-state: ${Buffer.from(JSON.stringify(state)).toString('base64')} -->\n`;
    } catch (e) {
      console.warn('Failed to serialize review state:', e);
      stateTag = '';
    }
  }

  // Check for existing comments from this bot to avoid spamming the PR
  let fetchUrl: string | null = `${url}?per_page=100`;
  let existingComment: { id: number; body: string; user: { type: string } } | undefined;

  while (fetchUrl) {
    const getCommentsResponse = await fetch(fetchUrl, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
      },
    });

    if (!getCommentsResponse.ok) break;

    const comments = await getCommentsResponse.json() as Array<{
      id: number;
      body: string;
      user: { type: string };
    }>;
    existingComment = comments.find(c =>
      c.user.type === 'Bot' && c.body.includes(`## ${reportTitle}`)
    );

    if (existingComment) break;

    const linkHeader = getCommentsResponse.headers.get('Link');
    const nextMatch = linkHeader?.match(/<([^>]+)>;\s*rel="next"/);
    fetchUrl = nextMatch ? nextMatch[1] : null;
  }

  if (existingComment) {
      const match = existingComment.body.match(/<!-- ai-review-count: (\d+) -->/);
      const currentCount = match ? parseInt(match[1], 10) : 1;
      const newCount = currentCount + 1;
      const updatedBody = `<!-- ai-review-count: ${newCount} -->\n${stateTag}${body}`;

      const updateUrl = `https://api.github.com/repos/${repo}/issues/comments/${existingComment.id}`;
      const updateResponse = await fetch(updateUrl, {
        method: 'PATCH',
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: 'application/vnd.github+json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ body: updatedBody }),
      });

      if (!updateResponse.ok) {
        const text = await updateResponse.text();
        throw new Error(`GitHub API error ${updateResponse.status}: ${text}`);
      }

      console.log('✅ Updated existing PR comment');
      return;
  }

  const newBody = `<!-- ai-review-count: 1 -->\n${stateTag}${body}`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ body: newBody }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`GitHub API error ${response.status}: ${text}`);
  }

  console.log('✅ Posted PR comment');
}
