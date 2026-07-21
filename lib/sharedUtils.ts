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

export function writeVerdictJson(artifactsDir: string, fileName: string, verdictData: any): void {
  const verdictPath = path.join(artifactsDir, `${fileName.replace('.md', '')}-verdict.json`);
  fs.writeFileSync(verdictPath, JSON.stringify(verdictData, null, 2));
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
    writeVerdictJson(artifactsDir, reportFileName, {
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
