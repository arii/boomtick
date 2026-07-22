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
  const normalizedArtifactsDir = path.resolve('artifacts');
  if (!resolvedPath.startsWith(normalizedArtifactsDir)) {
    throw new Error(`Security Error: attempt to write outside artifacts directory (${resolvedPath})`);
  }
  if (!data || typeof data !== 'object') {
    throw new Error('Invalid data: data must be an object');
  }
  await fs.promises.writeFile(resolvedPath, JSON.stringify(data, null, 2));
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
