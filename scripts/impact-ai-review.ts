import { orchestrateVisualReview } from '../lib/visualReviewOrchestrator';
import { geminiVisualReviewClient } from './clients/geminiVisualReviewClient';
import { githubModelsVisualReviewClient } from './clients/githubModelsVisualReviewClient';
import { runReviewScript, handleScriptError } from './utils/reviewScriptRunner';

const ALL_REVIEW_TITLES = [
  geminiVisualReviewClient.reportTitle,
  githubModelsVisualReviewClient.reportTitle,
];

async function main(): Promise<void> {
  const routeArgIdx = process.argv.indexOf('--route');
  const cliRoute = routeArgIdx !== -1 && process.argv[routeArgIdx + 1] ? process.argv[routeArgIdx + 1] : undefined;
  const targetRoute = cliRoute ?? process.env.TARGET_ROUTE ?? process.env.IMPACT_ROUTE;
  const force = process.argv.includes('--force') || Boolean(targetRoute) || process.env.FORCE_VISUAL_REVIEW === 'true';

  await runReviewScript({
    scriptName: 'review',
    geminiClient: geminiVisualReviewClient,
    githubModelsClient: githubModelsVisualReviewClient,
    orchestrateGemini: () => orchestrateVisualReview(geminiVisualReviewClient, ALL_REVIEW_TITLES, { targetRoute, force }),
  });
}

main().catch(error => handleScriptError(error, 'review'));
