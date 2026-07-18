import {
  parseCodeReviewVerdict,
  parseCodeReviewStateDetailed,
  budgetInputContext,
  extractFeedbackText,
} from '../../lib/codeReviewUtils';
import { buildSystemPrompt } from '../../lib/buildCodeReviewPrompt';
import type { CodeReviewSummary, CodeReviewResult } from '../../lib/codeReviewTypes';
import type { CodeReviewClientStrategy } from '../../lib/codeReviewOrchestrator';
import { runReview } from '../../src/reviewers/runner';
import { GitHubModelFactory } from '../../src/reviewers/factory';

export const githubModelsCodeReviewClient: CodeReviewClientStrategy = {
  botName: 'github-models-code-review',
  reportTitle: '🐙 GitHub Models Code Review',
  botTagline: 'Powered by GitHub Models',
  reportFileName: 'github-models-code-review.md',

  invokeReview: async (summary: CodeReviewSummary, forceMaxOutputTokens?: number): Promise<CodeReviewResult> => {
    const systemPrompt = buildSystemPrompt(summary);
    const { diffText, externalText } = budgetInputContext(systemPrompt, summary);

    if (forceMaxOutputTokens) {
      console.log(`[AI Review] Invoking with forced max output tokens budget: ${forceMaxOutputTokens}`);
    }

    const rules = [systemPrompt];

    const prContent = `DIFF:\n\n${diffText}` + (externalText ? `\n\nEXTERNAL CONTEXT:\n\n${externalText}` : '');

    console.log(`📌 Invoking runReview via GitHubModelFactory and Orchestration Runner...`);
    const feedback = await runReview({
      prContent,
      rules
    });

    const cleanFeedback = extractFeedbackText(feedback);
    const parsedState = parseCodeReviewStateDetailed(cleanFeedback);
    const fallbackChain = GitHubModelFactory.getFallbackChain();
    const primaryModel = fallbackChain[0] || "gpt-4o-mini";

    return {
      feedback: cleanFeedback,
      role: summary.role,
      tokens: 0,
      inputTokens: 0,
      outputTokens: 0,
      cacheTokens: 0,
      cost: 0,
      llmVerdict: parseCodeReviewVerdict(cleanFeedback),
      state: parsedState.state,
      modelName: primaryModel,
      truncated: false,
      parseError: parsedState.parseError,
    };
  }
};
