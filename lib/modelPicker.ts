import { pickGeminiModel } from './geminiModelPicker';

export async function pickOptimalGeminiModel(
  estimatedInputTokens: number = 0,
  _fallback: string = 'gemini-2.5-flash-lite'
): Promise<string> {
  const tier = estimatedInputTokens > 1000000 ? 'flash' : 'lite';
  return pickGeminiModel(tier, estimatedInputTokens);
}
