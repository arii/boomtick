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
  if (!process.env.GEMINI_API_KEY) {
    console.warn('⚠️  Skipping agent code review — GEMINI_API_KEY not set.');
    fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
    fs.writeFileSync(
      path.join(ARTIFACTS_DIR, geminiCodeReviewClient.reportFileName),
      `## ${geminiCodeReviewClient.reportTitle}\n\nSkipped: No GEMINI_API_KEY provided.\n`
    );
    return;
  }

  await orchestrateCodeReview(geminiCodeReviewClient, ALL_REVIEW_TITLES);
}

main().catch(error => {
  console.error(`❌ Agent code review failed: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
