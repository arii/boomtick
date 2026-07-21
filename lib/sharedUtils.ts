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

export function writeVerdictJson(verdictPath: string, data: any): void {
  fs.writeFileSync(verdictPath, JSON.stringify(data, null, 2));
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
    fs.writeFileSync(
      agentReportPath,
      `## ${reportTitle}\n\nSkipped: review quota (${maxReviews}) already met.\n`
    );
    const prevState = await getPrevState(reportTitle);
    writeVerdictJson(path.join(artifactsDir, `${reportFileName.replace('.md', '')}-verdict.json`), {
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
