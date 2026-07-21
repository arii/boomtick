
import { extractFinishReason, createGeminiModel, applyRetryStrategy } from './geminiUtils';
import { getGeminiPricing } from './geminiModelPicker';
import { extractFeedbackText, withRetry } from './codeReviewUtils';

export async function invokeGeminiModelWithRetry(
  modelName: string,
  maxOutputTokens: number,
  thinkingBudget: number,
  message: any
) {
  let model = createGeminiModel(modelName, maxOutputTokens, thinkingBudget);
  let response = await withRetry(() => model.invoke([message]), { maxRetries: 3, initialDelayMs: 1000 });
  let finishReason = extractFinishReason(response);

  if (finishReason === 'MAX_TOKENS') {
    console.warn('Gemini MAX_TOKENS — retrying with adjusted budget', { usage: response.usage_metadata });
    const { newMax, newThinking } = applyRetryStrategy(maxOutputTokens, thinkingBudget);
    thinkingBudget = newThinking;
    model = createGeminiModel(modelName, newMax, thinkingBudget);
    response = await withRetry(() => model.invoke([message]), { maxRetries: 3, initialDelayMs: 1000 });
    finishReason = extractFinishReason(response);
  }

  const usageMetadata = response.usage_metadata as any;
  const inputTokens = usageMetadata?.input_tokens ?? 0;
  const outputTokens = usageMetadata?.output_tokens ?? 0;
  const totalTokens = usageMetadata?.total_tokens ?? 0;
  const cacheTokens = usageMetadata?.cache_read_tokens ?? 0;
  const thoughtsTokenCount = usageMetadata?.thoughts_token_count ??
                             (typeof response.response_metadata === 'object' && response.response_metadata !== null
                               ? ((response.response_metadata as any).usage)?.thoughts_token_count
                               : 0) ?? 0;

  if (thoughtsTokenCount > thinkingBudget * 1.1) {
    console.warn('Thinking budget exceeded by >10%', {
      budgetSet: thinkingBudget,
      thoughtsUsed: thoughtsTokenCount,
      model: modelName,
    });
  }

  const isTruncated = finishReason === 'MAX_TOKENS' || finishReason === 'length' || finishReason === 'max_tokens';
  const pricing = getGeminiPricing(modelName);
  const cost = pricing ? (inputTokens / 1_000_000) * pricing.inputCostPerM + (outputTokens / 1_000_000) * pricing.outputCostPerM : 0;
  const feedback = extractFeedbackText(response.content) || (
    typeof response.content === 'string' ? response.content : JSON.stringify(response.content)
  );

  return {
    response,
    finishReason,
    usageMetadata,
    inputTokens,
    outputTokens,
    totalTokens,
    cacheTokens,
    thoughtsTokenCount,
    isTruncated,
    pricing,
    cost,
    feedback
  };
}

import { pickGeminiModel } from './geminiModelPicker';
export async function resolveGeminiModelAndBudget(
  preferredTier: 'flash' | 'lite',
  estimatedInputTokens: number,
  forceMaxOutputTokens: number | undefined,
  summary: any,
  systemPromptLength: number,
  estimateMaxOutputTokens: any
) {
  let modelName: string;
  try {
    modelName = await pickGeminiModel(preferredTier, estimatedInputTokens);
  } catch (err) {
    console.error('Failed to pick Gemini model, falling back based on input tokens:', err);
    modelName = estimatedInputTokens > 1000000 ? 'gemini-2.5-flash' : 'gemini-2.5-flash-lite';
  }

  let thinkingBudget = estimatedInputTokens > 10000 ? 4096 : 2048;
  const maxOutputTokens = forceMaxOutputTokens ?? estimateMaxOutputTokens(summary, systemPromptLength, thinkingBudget);
  return { modelName, thinkingBudget, maxOutputTokens };
}

import { parseVisualReviewFindings, parseLLMVerdict } from './visualReviewUtils';
export function parseVisualReviewReturn(
  summary: any,
  feedback: string,
  totalTokens: number,
  inputTokens: number,
  outputTokens: number,
  cacheTokens: number,
  cost: number,
  modelName: string,
  isTruncated: boolean
) {
  return {
    route: summary.route,
    severity: summary.severity,
    differencePercent: summary.differencePercent,
    feedback: feedback,
    tokens: totalTokens,
    inputTokens,
    outputTokens,
    cacheTokens,
    cost: cost,
    modelName: modelName,
    llmVerdict: parseLLMVerdict(feedback),
    findings: parseVisualReviewFindings(feedback),
    truncated: isTruncated,
  };
}
