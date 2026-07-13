import * as fs from 'fs';
import * as path from 'path';
import { ARTIFACTS_DIR } from '../../lib/visualReviewConstants';

export function writeMissingApiKeyVerdict(reportFileName: string, reportTitle: string, clientName: string): void {
  fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
  fs.writeFileSync(
    path.join(ARTIFACTS_DIR, reportFileName),
    `## ${reportTitle}\n\nSkipped: No ${clientName} provided.\n`
  );
  fs.writeFileSync(
    path.join(ARTIFACTS_DIR, `${reportFileName.replace('.md', '')}-verdict.json`),
    JSON.stringify({ passed: true, highCount: 0, routes: [], llmVerdict: 'warn', skipReason: 'MISSING_API_KEY' }, null, 2)
  );
}
