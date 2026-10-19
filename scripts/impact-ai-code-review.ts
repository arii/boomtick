import { orchestrateCodeReview } from '../lib/codeReviewOrchestrator';
import { geminiCodeReviewClient } from './clients/geminiCodeReviewClient';
import { runReviewScript, handleScriptError } from './utils/reviewScriptRunner';
import { initializeGitHubAuth } from '../lib/githubAuth';
import { sendJulesImpactReport } from '../lib/julesReviewClient';

const ALL_REVIEW_TITLES = [
  geminiCodeReviewClient.reportTitle,
];

async function main(): Promise<void> {
  await initializeGitHubAuth();

  const arg = process.argv[2];
  if (arg === 'jules') {
    if (process.env.JULES_API_KEY) {
      await sendJulesImpactReport(process.env.TASK_ID);
    }
    return;
  }

  await runReviewScript({
    scriptName: 'code review',
    geminiClient: geminiCodeReviewClient,
    orchestrateGemini: () => orchestrateCodeReview(geminiCodeReviewClient, ALL_REVIEW_TITLES),
  });

  const sendToJules = process.env.SEND_TO_JULES !== 'false';
  if (sendToJules && process.env.JULES_API_KEY) {
    await sendJulesImpactReport(process.env.TASK_ID);
  }
}

main().catch(error => handleScriptError(error, 'code review'));
