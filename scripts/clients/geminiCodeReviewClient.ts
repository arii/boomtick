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
import { invokeGeminiWithBudgetRetry, handleGeminiResponse } from '../../lib/geminiUtils';

import type { CodeReviewSummary, CodeReviewResult } from '../../lib/codeReviewTypes';
import type { CodeReviewClientStrategy } from '../../lib/codeReviewOrchestrator';

export const geminiCodeReviewClient: CodeReviewClientStrategy = {
  botName: 'gemini-code-review',
  reportTitle: '👁️ Gemini Code Review Agent',
  botTagline: 'Powered by Gemini 3.x',
  reportFileName: 'gemini-code-review.md',

  invokeReview: async (summary: CodeReviewSummary, forceMaxOutputTokens?: number): Promise<CodeReviewResult> => {
    const systemPrompt = buildSystemPrompt(summary);
    const { diffText, externalText } = budgetInputContext(systemPrompt, summary);

    const estimatedInputTokens = summary.estimatedInputTokens || calculateEstimatedTokens([systemPrompt, diffText, externalText || '']);
    // For code review, we prefer Flash if the diff is complex/large, otherwise Lite.
    const preferredTier = (estimatedInputTokens > 15000 || (summary.previousState?.findings.length ?? 0) > 5) ? 'flash' : 'lite';

    let modelName: string;
    try {
      modelName = await pickGeminiModel(preferredTier, estimatedInputTokens);
    } catch (err) {
      console.error('Failed to pick Gemini model, falling back based on input tokens:', err);
      modelName = estimatedInputTokens > 1000000 ? 'gemini-2.5-flash' : 'gemini-2.5-flash-lite';
    }

    let thinkingBudget = estimatedInputTokens > 10000 ? 4096 : 2048;
    const maxOutputTokens = forceMaxOutputTokens ?? estimateMaxOutputTokens(summary, systemPrompt.length, thinkingBudget);

    const baseContent = buildReviewPayload(systemPrompt, diffText, externalText).map(msg => msg.content).join('\n\n');
    const message = { content: baseContent };

    const retryResult = await invokeGeminiWithBudgetRetry(
      modelName,
      maxOutputTokens,
      thinkingBudget,
      message,
      withRetry
    );

    const parsedGemini = handleGeminiResponse(retryResult, modelName, thinkingBudget);

    if (parsedGemini.isTruncated) {
      // Do not throw here, instead pass the error state gracefully
      // so it can be handled by orchestrator without breaking the CI suite
      return {
        feedback: parsedGemini.feedback,
        role: summary.role,
        tokens: parsedGemini.tokens,
        cost: 0,
        modelName,
        llmVerdict: 'warn',
        isTruncated: true,
        findings: [],
      };
    }

    const parsedState = parseCodeReviewStateDetailed(parsedGemini.feedback);

    return {
      feedback: parsedGemini.feedback,
      role: summary.role,
      tokens: parsedGemini.tokens,
      inputTokens: parsedGemini.inputTokens,
      outputTokens: parsedGemini.outputTokens,
      cacheTokens: parsedGemini.cacheTokens,
      cost: parsedGemini.cost,
      modelName: modelName,
      llmVerdict: parseCodeReviewVerdict(parsedGemini.feedback),
      findings: parsedState.state?.findings ?? [],
      isTruncated: parsedGemini.isTruncated,
      parseError: parsedState.parseError,
    };
  }
};
