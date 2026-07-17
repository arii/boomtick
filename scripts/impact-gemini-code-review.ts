import { orchestrateCodeReview } from '../lib/codeReviewOrchestrator';
import { githubModelsCodeReviewClient } from './clients/githubModelsCodeReviewClient';
import { geminiCodeReviewClient } from './clients/geminiCodeReviewClient';
import { writeMissingApiKeyVerdict } from './utils/verdict';

const ALL_REVIEW_TITLES = [
  geminiCodeReviewClient.reportTitle,
  githubModelsCodeReviewClient.reportTitle,
];

async function main(): Promise<void> {
  if (!process.env.GEMINI_API_KEY) {
    console.warn('⚠️  Skipping agent code review — GEMINI_API_KEY not set.');
    writeMissingApiKeyVerdict(
      geminiCodeReviewClient.reportFileName,
      geminiCodeReviewClient.reportTitle,
      'GEMINI_API_KEY'
    );
    return;
  }

  await orchestrateCodeReview(geminiCodeReviewClient, ALL_REVIEW_TITLES);
}

main().catch(error => {
  console.error(`❌ Agent code review failed: ${error instanceof Error ? error.message : String(error)}`);
  // Do not crash the process if the agent review fails (e.g. Rate limits)
  // Just exit with code 0 so the rest of the workflow can finish.
  process.exit(0);
});
