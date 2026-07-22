import { orchestrateCodeReview } from '../lib/codeReviewOrchestrator';
import { githubModelsCodeReviewClient } from './clients/githubModelsCodeReviewClient';
import { geminiCodeReviewClient } from './clients/geminiCodeReviewClient';
import { writeMissingApiKeyVerdict } from './utils/verdict';

const ALL_REVIEW_TITLES = [
  geminiCodeReviewClient.reportTitle,
  githubModelsCodeReviewClient.reportTitle,
];

async function main(): Promise<void> {
  const provider = process.argv[2];

  if (provider === 'gemini') {
    // security-safe: Environment variables are trusted in this workflow context.
    if (!process.env.GEMINI_API_KEY) {
      console.warn('⚠️  Skipping agent code review — GEMINI_API_KEY not set.');
      try {
        await writeMissingApiKeyVerdict(
          geminiCodeReviewClient.reportFileName,
          geminiCodeReviewClient.reportTitle,
          'GEMINI_API_KEY'
        );
      } catch (err) {
        console.error('Failed to write missing API key verdict', err);
      }
      return;
    }
    await orchestrateCodeReview(geminiCodeReviewClient, ALL_REVIEW_TITLES);
  } else if (provider === 'github-models') {
    // security-safe: Environment variables are trusted in this workflow context.
    if (!process.env.GITHUB_TOKEN) {
      console.warn('⚠️  Skipping agent code review — GITHUB_TOKEN not set.');
      try {
        await writeMissingApiKeyVerdict(
          githubModelsCodeReviewClient.reportFileName,
          githubModelsCodeReviewClient.reportTitle,
          'GITHUB_TOKEN'
        );
      } catch (err) {
        console.error('Failed to write missing API key verdict', err);
      }
      return;
    }
    await orchestrateCodeReview(githubModelsCodeReviewClient, ALL_REVIEW_TITLES);
  } else {
    console.error('❌ Unknown provider specified.');
    process.exit(1);
  }
}

main().catch(error => {
  console.error(`❌ Agent code review failed: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(0);
});
