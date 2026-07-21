import { orchestrateVisualReview } from '../lib/visualReviewOrchestrator';
import { geminiVisualReviewClient } from './clients/geminiVisualReviewClient';
import { githubModelsVisualReviewClient } from './clients/githubModelsVisualReviewClient';
import { writeMissingApiKeyVerdict } from './utils/verdict';

const ALL_REVIEW_TITLES = [
  geminiVisualReviewClient.reportTitle,
  githubModelsVisualReviewClient.reportTitle,
];

async function main(): Promise<void> {
  const provider = process.argv[2];

  if (provider === 'gemini') {
    if (!process.env.GEMINI_API_KEY) {
      console.warn('⚠️  Skipping agent review — GEMINI_API_KEY not set.');
      await writeMissingApiKeyVerdict(
        geminiVisualReviewClient.reportFileName,
        geminiVisualReviewClient.reportTitle,
        'GEMINI_API_KEY'
      );
      return;
    }
    await orchestrateVisualReview(geminiVisualReviewClient, ALL_REVIEW_TITLES);
  } else if (provider === 'github-models') {
    if (!process.env.GITHUB_TOKEN) {
      console.warn('⚠️  Skipping agent review — GITHUB_TOKEN not set.');
      await writeMissingApiKeyVerdict(
        githubModelsVisualReviewClient.reportFileName,
        githubModelsVisualReviewClient.reportTitle,
        'GITHUB_TOKEN'
      );
      return;
    }
    await orchestrateVisualReview(githubModelsVisualReviewClient, ALL_REVIEW_TITLES);
  } else {
    console.error('❌ Unknown provider specified.');
    process.exit(1);
  }
}

main().catch(error => {
  console.error(`❌ Agent review failed: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(0);
});
