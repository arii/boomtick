import {
  parseCodeReviewVerdict,
  parseCodeReviewStateDetailed,
  estimateMaxOutputTokens,
  budgetInputContext,
  buildReviewPayload,
  calculateEstimatedTokens,
  extractFeedbackText
} from '../codeReviewUtils';

import { buildSystemPrompt } from '../buildCodeReviewPrompt';
import { pickGeminiModel, getGeminiPricing } from '../geminiModelPicker';
import { invokeGeminiWithBudgetRetry, createGeminiModel } from '../geminiUtils';

import type { CodeReviewSummary, CodeReviewResult } from '../codeReviewTypes';
import type { CodeReviewClientStrategy } from '../codeReviewOrchestrator';

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
    const { HumanMessage } = await import('@langchain/core/messages');
    const message = new HumanMessage({ content: baseContent });

    const { response, finishReason, thinkBudget: finalThinkingBudget } = await invokeGeminiWithBudgetRetry(
      (maxOut, think) => createGeminiModel(modelName, maxOut, think),
      maxOutputTokens,
      thinkingBudget,
      message
    );

    const usageMetadata = response.usage_metadata as {
      input_tokens?: number;
      output_tokens?: number;
      total_tokens?: number;
      thoughts_token_count?: number;
      cache_read_tokens?: number;
    };

    const inputTokens = usageMetadata?.input_tokens ?? 0;
    const outputTokens = usageMetadata?.output_tokens ?? 0;
    const totalTokens = usageMetadata?.total_tokens ?? 0;
    const cacheTokens = usageMetadata?.cache_read_tokens ?? 0;
    // thoughtsTokenCount might be nested in response_metadata or usage_metadata
    const thoughtsTokenCount = usageMetadata?.thoughts_token_count ??
                               (typeof response.response_metadata === 'object' && response.response_metadata !== null
                                 ? ((response.response_metadata as Record<string, unknown>).usage as Record<string, unknown>)?.thoughts_token_count as number | undefined
                                 : 0) ?? 0;

    if (thoughtsTokenCount > finalThinkingBudget * 1.1) {
      console.warn('Thinking budget exceeded by >10%', {
        budgetSet: finalThinkingBudget,
        thoughtsUsed: thoughtsTokenCount,
        model: modelName,
      });
    }

    const isTruncated = finishReason === 'MAX_TOKENS' || finishReason === 'length' || finishReason === 'max_tokens';

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

    const pricing = getGeminiPricing(modelName);
    const cost = pricing ? (inputTokens / 1_000_000) * pricing.inputCostPerM + (outputTokens / 1_000_000) * pricing.outputCostPerM : 0;

    // Safe to parse from here. The response.content.parts structure isn't exposed properly via Langchain here
    // typically in @langchain response.content is a string, but if we extract only text it's better
    const feedback = extractFeedbackText(response.content) || (
      typeof response.content === 'string' ? response.content : JSON.stringify(response.content)
    );

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
