import * as fs from 'fs';
import * as path from 'path';
import { ARTIFACTS_DIR } from './visualReviewConstants';

export function skipReviewAndWriteVerdict(
  reportPath: string,
  reportTitle: string,
  reportFileName: string,
  skipReason: string,
  prevState: any
): void {
  fs.writeFileSync(
    reportPath,
    `## ${reportTitle}\n\n${skipReason}\n`
  );
  fs.writeFileSync(path.join(ARTIFACTS_DIR, `${reportFileName.replace('.md', '')}-verdict.json`), JSON.stringify({
    passed: true,
    highCount: 0,
    routes: [],
    llmVerdict: 'pass',
    state: prevState || { findings: [] }
  }, null, 2));
}
