import { orchestrateVisualReview } from '../lib/visualReviewOrchestrator';
import { geminiVisualReviewClient } from './clients/geminiVisualReviewClient';
import { githubModelsVisualReviewClient } from './clients/githubModelsVisualReviewClient';
import { writeMissingApiKeyVerdict, writeDeprecatedVerdict } from './utils/verdict';

const ALL_REVIEW_TITLES = [
  geminiVisualReviewClient.reportTitle,
  githubModelsVisualReviewClient.reportTitle,
];

async function main(): Promise<void> {
  const provider = process.argv[2];

  if (provider === 'gemini') {
    // security-safe: Environment variables are trusted in this workflow context.
    if (!process.env.GEMINI_API_KEY) {
      console.warn('⚠️  Skipping agent review — GEMINI_API_KEY not set.');
      try {
        await writeMissingApiKeyVerdict(
          geminiVisualReviewClient.reportFileName,
          geminiVisualReviewClient.reportTitle,
          'GEMINI_API_KEY'
        );
      } catch (err) {
        console.error('Failed to write missing API key verdict', err);
      }
      return;
    }
    await orchestrateVisualReview(geminiVisualReviewClient, ALL_REVIEW_TITLES);
  } else if (provider === 'github-models') {
    console.warn('⚠️  Skipping agent review — GitHub Models/OpenAI review is disabled. Only Gemini review is active.');
    try {
      await writeDeprecatedVerdict(
        githubModelsVisualReviewClient.reportFileName,
        githubModelsVisualReviewClient.reportTitle,
        'GitHub Models'
      );
    } catch (err) {
      console.error('Failed to write deprecated verdict', err);
    }
    return;
  } else {
    console.error('❌ Unknown provider specified.');
    process.exit(1);
  }
}

main().catch(error => {
  console.error(`❌ Agent review failed: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
