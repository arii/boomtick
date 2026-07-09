import * as fs from 'fs';
import * as path from 'path';
import { ARTIFACTS_DIR } from '../lib/visualReviewConstants';
import { orchestrateCodeReview } from '../lib/codeReviewOrchestrator';
import { githubModelsCodeReviewClient } from './clients/githubModelsCodeReviewClient';
import { geminiCodeReviewClient } from './clients/geminiCodeReviewClient';

const ALL_REVIEW_TITLES = [
  geminiCodeReviewClient.reportTitle,
  githubModelsCodeReviewClient.reportTitle,
];

async function main(): Promise<void> {
  if (!process.env.GITHUB_TOKEN) {
    console.warn('⚠️  Skipping agent code review — GITHUB_TOKEN not set.');
    fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
    fs.writeFileSync(
      path.join(ARTIFACTS_DIR, githubModelsCodeReviewClient.reportFileName),
      `## ${githubModelsCodeReviewClient.reportTitle}\n\nSkipped: No GITHUB_TOKEN provided.\n`
    );
    return;
  }

  await orchestrateCodeReview(githubModelsCodeReviewClient, ALL_REVIEW_TITLES);
}

main().catch(error => {
  console.error(`❌ Agent code review failed: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
