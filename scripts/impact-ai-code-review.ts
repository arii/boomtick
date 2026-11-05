import { orchestrateCodeReview } from '../lib/codeReviewOrchestrator';
import { geminiCodeReviewClient } from './clients/geminiCodeReviewClient';
import { runReviewScript, handleScriptError } from './utils/reviewScriptRunner';
import { initializeGitHubAuth } from '../lib/githubAuth';

const ALL_REVIEW_TITLES = [
  geminiCodeReviewClient.reportTitle,
];

async function main(): Promise<void> {
  await initializeGitHubAuth();

  await runReviewScript({
    scriptName: 'code review',
    geminiClient: geminiCodeReviewClient,
    orchestrateGemini: () => orchestrateCodeReview(geminiCodeReviewClient, ALL_REVIEW_TITLES),
  });
}

main().catch(error => handleScriptError(error, 'code review'));
