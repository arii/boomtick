import { ChatGoogleGenerativeAI } from '@langchain/google-genai';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function extractFinishReason(res: any): string {
  if (res.response_metadata?.finishReason) return res.response_metadata.finishReason;
  if (res.response_metadata?.finish_reason) return res.response_metadata.finish_reason;
  if (res.generationInfo?.finishReason) return res.generationInfo.finishReason;
  const candidate = res.response_metadata?.candidates?.[0];
  if (candidate?.finishReason) return candidate.finishReason;
  return 'UNKNOWN';
}

export function createGeminiModel(
  modelName: string,
  maxOutputTokens: number,
  thinkingBudget: number
): ChatGoogleGenerativeAI {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) throw new Error('Missing GEMINI_API_KEY environment variable');

  return new ChatGoogleGenerativeAI({
    model: modelName,
    apiKey,
    maxOutputTokens,
    thinkingConfig: { includeThoughts: true, thinkingBudget }
  });
}

export function getConfiguredTokens(type: 'code' | 'visual'): { maxOutputTokens: number; thinkingBudget: number } {
  let maxOutputTokens = type === 'code' ? 6000 : 4096;
  let thinkingBudget = type === 'code' ? 2048 : 1024;
  if (process.env.GEMINI_MAX_OUTPUT_TOKENS) {
    const val = parseInt(process.env.GEMINI_MAX_OUTPUT_TOKENS, 10);
    if (!isNaN(val)) maxOutputTokens = val;
  }
  if (process.env.GEMINI_THINKING_BUDGET) {
    const val = parseInt(process.env.GEMINI_THINKING_BUDGET, 10);
    if (!isNaN(val)) thinkingBudget = val;
  }
  return { maxOutputTokens, thinkingBudget };
}

export function applyRetryStrategy(currentMax: number, currentThinking: number): { newMax: number; newThinking: number } {
  const newMax = Math.min(Math.round(currentMax * 1.25), 8192);
  const newThinking = Math.round(currentThinking * 0.5);
  return { newMax, newThinking };
}

export async function invokeGeminiWithBudgetRetry<T>(
  modelFactory: (maxOut: number, thinkBudget: number) => ChatGoogleGenerativeAI,
  initialMaxOut: number,
  initialThinkBudget: number,
  message: any
) {
  const { withRetry } = await import('./codeReviewUtils');
  let maxOut = initialMaxOut;
  let thinkBudget = initialThinkBudget;
  let model = modelFactory(maxOut, thinkBudget);

  let response = await withRetry(() => model.invoke([message]), { maxRetries: 3, initialDelayMs: 1000 });
  let finishReason = extractFinishReason(response);

  if (finishReason === 'MAX_TOKENS') {
    console.warn('Gemini MAX_TOKENS — retrying with adjusted budget', { usage: response.usage_metadata });
    const { newMax, newThinking } = applyRetryStrategy(maxOut, thinkBudget);
    maxOut = newMax;
    thinkBudget = newThinking;
    model = modelFactory(maxOut, thinkBudget);
    response = await withRetry(() => model.invoke([message]), { maxRetries: 3, initialDelayMs: 1000 });
    finishReason = extractFinishReason(response);
  }

  return { response, finishReason, maxOut, thinkBudget };
}
