import { prepareReviewContext } from '../../lib/geminiClientUtils';
import {
  parseCodeReviewVerdict,
  parseCodeReviewStateDetailed,
  estimateMaxOutputTokens,
  budgetInputContext,
  buildReviewPayload,
  calculateEstimatedTokens,
  extractFeedbackText,
  withRetry
} from '../../lib/codeReviewUtils';

import { buildSystemPrompt } from '../../lib/buildCodeReviewPrompt';

import { pickGeminiModel, getGeminiPricing } from '../../lib/geminiModelPicker';
import { extractFinishReason, createGeminiModel, applyRetryStrategy } from '../../lib/geminiUtils';
import { invokeGeminiModelWithRetry } from '../../lib/geminiClientUtils';
import { invokeGeminiModelWithRetry } from '../../lib/geminiClientUtils';
import { invokeGeminiModelWithRetry } from '../../lib/geminiClientUtils';
import { invokeGeminiModelWithRetry } from '../../lib/geminiClientUtils';

import type { CodeReviewSummary, CodeReviewResult } from '../../lib/codeReviewTypes';
import type { CodeReviewClientStrategy } from '../../lib/codeReviewOrchestrator';

export const geminiCodeReviewClient: CodeReviewClientStrategy = {
  botName: 'gemini-code-review',
  reportTitle: '👁️ Gemini Code Review Agent',
  botTagline: 'Powered by Gemini 3.x',
  reportFileName: 'gemini-code-review.md',

  invokeReview: async (summary: CodeReviewSummary, forceMaxOutputTokens?: number): Promise<CodeReviewResult> => {
    const { systemPrompt, diffText, externalText } = prepareReviewContext(summary, buildSystemPrompt, budgetInputContext);

    const estimatedInputTokens = summary.estimatedInputTokens || calculateEstimatedTokens([systemPrompt, diffText, externalText || '']);
    // For code review, we prefer Flash if the diff is complex/large, otherwise Lite.
    const preferredTier = (estimatedInputTokens > 15000 || (summary.previousState?.findings.length ?? 0) > 5) ? 'flash' : 'lite';

    const { modelName, thinkingBudget, maxOutputTokens } = await resolveGeminiModelAndBudget(preferredTier, estimatedInputTokens, forceMaxOutputTokens, summary, systemPrompt.length, estimateMaxOutputTokens);

        const {
      finishReason,
      usageMetadata,
      inputTokens,
      outputTokens,
      totalTokens,
      cacheTokens,
      isTruncated,
      cost,
      feedback
    } = await invokeGeminiModelWithRetry(modelName, maxOutputTokens, thinkingBudget, message);

    if (isTruncated) {
      console.error('Gemini truncation', {
        finishReason,
        usage: usageMetadata,
      });
      // Do not throw here, instead pass the error state gracefully
      // so it can be handled by orchestrator without breaking the CI suite
      return {

        feedback: `Error: Gemini model was truncated during execution (finishReason=${finishReason}).`,
        tokens: totalTokens,
        cost: 0,
        modelName,
        llmVerdict: 'warn',
        truncated: true,
      };
    }

    return {
        feedback: `Error: Gemini model was truncated during execution (finishReason=${finishReason}).`,
        tokens: totalTokens,
        cost: 0,
        modelName,
        llmVerdict: 'warn',
        truncated: true,
      };
    }

    const parsedState = parseCodeReviewStateDetailed(feedback);

    return {
      feedback: feedback,
      role: summary.role,
      tokens: totalTokens,
      inputTokens,
      outputTokens,
      cacheTokens,
      cost: cost,
      modelName: modelName,
      llmVerdict: parseCodeReviewVerdict(feedback),
      state: parsedState.state,
      truncated: isTruncated,
      parseError: parsedState.parseError,
    };
  }
};
