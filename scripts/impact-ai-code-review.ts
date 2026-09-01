import { orchestrateCodeReview } from '../lib/codeReviewOrchestrator';
import { githubModelsCodeReviewClient } from './clients/githubModelsCodeReviewClient';
import { geminiCodeReviewClient } from './clients/geminiCodeReviewClient';
import { runReviewScript, handleScriptError } from './utils/reviewScriptRunner';

const ALL_REVIEW_TITLES = [
  geminiCodeReviewClient.reportTitle,
  githubModelsCodeReviewClient.reportTitle,
];

async function main(): Promise<void> {
  await runReviewScript({
    scriptName: 'code review',
    geminiClient: geminiCodeReviewClient,
    githubModelsClient: githubModelsCodeReviewClient,
    orchestrateGemini: () => orchestrateCodeReview(geminiCodeReviewClient, ALL_REVIEW_TITLES),
  });
}

main().catch(error => handleScriptError(error, 'code review'));
