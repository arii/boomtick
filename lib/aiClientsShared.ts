import { extractFinishReason, applyRetryStrategy } from './geminiUtils';

export function checkAndHandleTruncation(
  finishReason: string | null | undefined,
  usageMetadata: any,
  modelName: string
): { isTruncated: boolean; totalTokens: number } {
  const isTruncated = finishReason === 'MAX_TOKENS' || finishReason === 'length' || finishReason === 'max_tokens';

  const totalTokens = usageMetadata?.total_tokens ?? 0;

  if (isTruncated) {
    console.error('Gemini truncation', {
      finishReason,
      usage: usageMetadata,
    });
  }

  return { isTruncated, totalTokens };
}
