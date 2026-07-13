import { orchestrateVisualReview } from '../lib/visualReviewOrchestrator';
import { githubModelsVisualReviewClient } from './clients/githubModelsVisualReviewClient';
import { geminiVisualReviewClient } from './clients/geminiVisualReviewClient';
import { writeMissingApiKeyVerdict } from './utils/verdict';

const ALL_REVIEW_TITLES = [
  geminiVisualReviewClient.reportTitle,
  githubModelsVisualReviewClient.reportTitle,
];

async function main(): Promise<void> {
  if (!process.env.GITHUB_TOKEN) {
    console.warn('⚠️  Skipping agent review — GITHUB_TOKEN not set.');
    writeMissingApiKeyVerdict(
      githubModelsVisualReviewClient.reportFileName,
      githubModelsVisualReviewClient.reportTitle,
      'GITHUB_TOKEN'
    );
    return;
  }

  await orchestrateVisualReview(githubModelsVisualReviewClient, ALL_REVIEW_TITLES);
}

main().catch(error => {
  console.error(`❌ Agent review failed: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
