import { orchestrateVisualReview } from '../lib/visualReviewOrchestrator';
import { geminiVisualReviewClient } from './clients/geminiVisualReviewClient';
import { githubModelsVisualReviewClient } from './clients/githubModelsVisualReviewClient';
import { writeMissingApiKeyVerdict } from './utils/verdict';

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
    writeMissingApiKeyVerdict(
      geminiVisualReviewClient.reportFileName,
      geminiVisualReviewClient.reportTitle,
      'GEMINI_API_KEY'
    );
    return;
  }

  await orchestrateVisualReview(geminiVisualReviewClient, ALL_REVIEW_TITLES);
}

main().catch(error => {
  console.error(`❌ Agent review failed: ${error instanceof Error ? error.message : String(error)}`);
  // Do not crash the process if the agent review fails (e.g. Rate limits)
  // Just exit with code 0 so the rest of the workflow can finish.
  process.exit(0);
});
