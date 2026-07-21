import * as fs from 'fs';
import * as path from 'path';
import { ARTIFACTS_DIR } from '../../lib/visualReviewConstants';
import { writeVerdictJson } from '../../lib/sharedUtils';

export async function writeMissingApiKeyVerdict(reportFileName: string, reportTitle: string, clientName: string): Promise<void> {
  if (!reportFileName || !reportTitle || !clientName) {
    throw new Error('writeMissingApiKeyVerdict requires valid non-empty string arguments.');
  }

  // Ensure reportFileName does not contain path traversal vectors
  const safeFileName = path.basename(reportFileName);

  await fs.promises.mkdir(ARTIFACTS_DIR, { recursive: true });
  await fs.promises.writeFile(
    path.join(ARTIFACTS_DIR, safeFileName),
    `## ${reportTitle}\n\nSkipped: No ${clientName} provided.\n`
  );
  await writeVerdictJson(
    path.join(ARTIFACTS_DIR, `${safeFileName.replace('.md', '')}-verdict.json`),
    { passed: true, highCount: 0, routes: [], llmVerdict: 'warn', skipReason: 'MISSING_API_KEY', state: { findings: [] } }
  );
}
