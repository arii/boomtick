import * as fs from 'fs';
import * as path from 'path';
import { ARTIFACTS_DIR } from '../../lib/visualReviewConstants';
import { isOpenBlockingFinding, writeVerdictJson } from '../../lib/sharedUtils';
import type { CodeReviewState } from '../../lib/codeReviewTypes';

export async function writeMissingApiKeyVerdict(reportFileName: string, reportTitle: string, clientName: string, prevState?: CodeReviewState): Promise<void> {
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
  const highCount = prevState?.findings?.filter(isOpenBlockingFinding).length ?? 0;
  await writeVerdictJson(
    path.join(ARTIFACTS_DIR, `${safeFileName.replace('.md', '')}-verdict.json`),
    { passed: false, highCount, routes: [], llmVerdict: highCount > 0 ? 'fail' : 'warn', skipReason: 'MISSING_API_KEY', state: highCount > 0 ? prevState : { findings: [] } }
  );
}
