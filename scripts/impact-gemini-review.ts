import * as fs from 'fs';
import * as path from 'path';
import { ARTIFACTS_DIR } from '../lib/visualReviewConstants';
import { orchestrateVisualReview } from '../lib/visualReviewOrchestrator';
import { geminiVisualReviewClient } from './clients/geminiVisualReviewClient';
import { githubModelsVisualReviewClient } from './clients/githubModelsVisualReviewClient';

const ALL_REVIEW_TITLES = [
  geminiVisualReviewClient.reportTitle,
  githubModelsVisualReviewClient.reportTitle,
];

async function main(): Promise<void> {
  if (!process.env.GEMINI_API_KEY) {
    console.warn('⚠️  Skipping agent review — GEMINI_API_KEY not set.');
    // The orchestrator handles missing visual summary gracefully,
    // but if the API key is strictly missing we should probably just exit or stub a file
    // to match original behavior.
    fs.writeFileSync(
      path.join(ARTIFACTS_DIR, geminiVisualReviewClient.reportFileName),
      `## ${geminiVisualReviewClient.reportTitle}\n\nSkipped: No GEMINI_API_KEY provided.\n`
    );
    return;
  }

  await orchestrateVisualReview(geminiVisualReviewClient, ALL_REVIEW_TITLES);
}

main().catch(error => {
  console.error(`❌ Agent review failed: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
