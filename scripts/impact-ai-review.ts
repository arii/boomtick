import { orchestrateVisualReview } from '../lib/visualReviewOrchestrator';
import { geminiVisualReviewClient } from './clients/geminiVisualReviewClient';
import { githubModelsVisualReviewClient } from './clients/githubModelsVisualReviewClient';
import { runReviewScript, handleScriptError } from './utils/reviewScriptRunner';

const ALL_REVIEW_TITLES = [
  geminiVisualReviewClient.reportTitle,
  githubModelsVisualReviewClient.reportTitle,
];

async function main(): Promise<void> {
  await runReviewScript({
    scriptName: 'review',
    geminiClient: geminiVisualReviewClient,
    githubModelsClient: githubModelsVisualReviewClient,
    orchestrateGemini: () => orchestrateVisualReview(geminiVisualReviewClient, ALL_REVIEW_TITLES),
  });
}

main().catch(error => handleScriptError(error, 'review'));
