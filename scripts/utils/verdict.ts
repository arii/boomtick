import * as fs from 'fs';
import * as path from 'path';
import { ARTIFACTS_DIR } from '../../lib/visualReviewConstants';
import { writeVerdictJson } from '../../lib/sharedUtils';

export async function writeMissingApiKeyVerdict(reportFileName: string, reportTitle: string, clientName: string): Promise<void> {
  if (!reportFileName || !reportTitle || !clientName) {
    throw new Error('writeMissingApiKeyVerdict requires valid non-empty string arguments.');
  }

  // security-safe: path.basename safely extracts the file name and prevents path traversal
  const safeFileName = path.basename(reportFileName);

  // security-safe: creating the directory safely if it does not exist
  try {
    await fs.promises.mkdir(ARTIFACTS_DIR, { recursive: true });
  } catch (err: any) {
    if (err.code !== 'EEXIST') throw err;
  }
  await fs.promises.writeFile(
    path.join(ARTIFACTS_DIR, safeFileName),
    `## ${reportTitle}\n\nSkipped: No ${clientName} provided.\n`
  );
  await writeVerdictJson(
    path.join(ARTIFACTS_DIR, `${safeFileName.replace('.md', '')}-verdict.json`),
    { passed: true, highCount: 0, routes: [], llmVerdict: 'warn', skipReason: 'MISSING_API_KEY', state: { findings: [] } }
  );
}
