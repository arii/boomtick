import * as fs from 'fs';
import * as path from 'path';

export async function runWithConcurrencyLimit(
  taskQueue: Array<() => Promise<void>>,
  limit: number
): Promise<void> {
  const workers = Array.from({ length: Math.min(limit, taskQueue.length) }, async () => {
    while (taskQueue.length > 0) {
      const task = taskQueue.shift();
      if (task) await task();
    }
  });

  await Promise.all(workers);
}

export async function writeVerdictJson(verdictPath: string, data: any): Promise<void> {
  const resolvedPath = path.resolve(verdictPath);
  // security-safe: The absolute path is validated against normalizedArtifactsDir root to prevent path traversal
  const normalizedArtifactsDir = path.resolve('artifacts');
  if (!resolvedPath.startsWith(normalizedArtifactsDir)) {
    throw new Error(`Security Error: attempt to write outside artifacts directory (${resolvedPath})`);
  }
  if (!data || typeof data !== 'object') {
    throw new Error('Invalid data: data must be an object');
  }
  await fs.promises.writeFile(resolvedPath, JSON.stringify(data, null, 2));
}

export async function writeGracefulExitVerdict(
  reportFileName: string,
  artifactsDir: string,
  prevState: any,
  isTruncated: boolean = false,
  skipReason?: string
): Promise<void> {
  const safeReportFileName = path.basename(reportFileName);
  const verdictPath = path.join(artifactsDir, `${safeReportFileName.replace('.md', '')}-verdict.json`);
  await writeVerdictJson(verdictPath, {
    passed: true,
    highCount: 0,
    routes: [],
    llmVerdict: 'pass',
    isTruncated,
    skipReason,
    state: prevState || { findings: [] }
  });
}

export async function checkReviewQuota(
  existingCount: number,
  maxReviews: number,
  botName: string,
  reportTitle: string,
  agentReportPath: string,
  reportFileName: string,
  artifactsDir: string,
  getPrevState: (title: string) => Promise<any>
): Promise<boolean> {
  if (existingCount >= maxReviews) {
    console.log(`⏭️  Skipping ${botName} — ${existingCount}/${maxReviews} reviews already posted.`);
    await fs.promises.writeFile(
      agentReportPath,
      `## ${reportTitle}\n\nSkipped: review quota (${maxReviews}) already met.\n`
    );
    const prevState = await getPrevState(reportTitle);
    await writeVerdictJson(path.join(artifactsDir, `${reportFileName.replace('.md', '')}-verdict.json`), {
      passed: true,
      highCount: 0,
      routes: [],
      llmVerdict: 'pass',
      state: prevState || { findings: [] }
    });
    return true; // Quota met, skip review
  }
  return false; // Quota not met, continue review
}

export function createTaskErrorResult<T extends { role?: string; feedback: string; tokens: number; cost: number; inputTokens: number; outputTokens: number; cacheTokens: number; modelName: string; llmVerdict: 'warn' }>(
  role: string,
  err: unknown,
  reviewType: string,
  extraFields: Omit<T, 'role' | 'feedback' | 'tokens' | 'cost' | 'inputTokens' | 'outputTokens' | 'cacheTokens' | 'modelName' | 'llmVerdict'>
): T {
  const errorMsg = err instanceof Error ? err.message : String(err);
  console.error(`❌ Error in ${role} ${reviewType} task:`, err);

  return {
    ...extraFields,
    feedback: `Error: failed to execute ${role} ${reviewType}. Details: ${errorMsg}`,
    role,
    tokens: 0,
    cost: 0,
    inputTokens: 0,
    outputTokens: 0,
    cacheTokens: 0,
    modelName: 'unknown',
    llmVerdict: 'warn',
  } as T;
}
