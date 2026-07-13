import { orchestrateCodeReview } from '../lib/codeReviewOrchestrator';
import { githubModelsCodeReviewClient } from './clients/githubModelsCodeReviewClient';
import { geminiCodeReviewClient } from './clients/geminiCodeReviewClient';
import { writeMissingApiKeyVerdict } from './utils/verdict';

const ALL_REVIEW_TITLES = [
  geminiCodeReviewClient.reportTitle,
  githubModelsCodeReviewClient.reportTitle,
];

async function main(): Promise<void> {
  if (!process.env.GITHUB_TOKEN) {
    console.warn('⚠️  Skipping agent code review — GITHUB_TOKEN not set.');
    writeMissingApiKeyVerdict(
      githubModelsCodeReviewClient.reportFileName,
      githubModelsCodeReviewClient.reportTitle,
      'GITHUB_TOKEN'
    );
    return;
  }

  await orchestrateCodeReview(githubModelsCodeReviewClient, ALL_REVIEW_TITLES);
}

main().catch(error => {
  console.error(`❌ Agent code review failed: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
