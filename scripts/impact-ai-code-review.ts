import { orchestrateCodeReview } from '../lib/codeReviewOrchestrator';
import { geminiCodeReviewClient } from './clients/geminiCodeReviewClient';
import { runReviewScript, handleScriptError } from './utils/reviewScriptRunner';
import { initializeGitHubAuth } from '../lib/githubAuth';
import { finalizeVerdictGate } from '../lib/verdictGate';

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

  finalizeVerdictGate({
    reportFileName: geminiCodeReviewClient.reportFileName,
    failOnVerdict: process.env.BOOMTICK_FAIL_ON_VERDICT === 'true',
  });
}

main().catch(error => handleScriptError(error, 'code review'));
