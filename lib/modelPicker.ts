
import { pickGeminiModel } from './geminiModelPicker';

export interface GitHubModel {
  id: string;
  name: string;
  publisher: string;
  rate_limit_tier: 'high' | 'low';
  supported_input_modalities: string[];
  capabilities: string[];
  limits?: {
    max_input_tokens?: number;
    max_output_tokens?: number;
  };
}

export function getAvailableModels(_token: string): Promise<GitHubModel[]> {
  return Promise.resolve([]);
}

export async function pickOptimalModel(
  _token: string,
  fallback: string = 'gpt-4o-mini',
  _needsVision: boolean = false,
  _estimatedInputTokens: number = 0
): Promise<string> {
  return fallback;
}

export async function pickOptimalGeminiModel(
  estimatedInputTokens: number = 0,
  _fallback: string = 'gemini-2.5-flash-lite'
): Promise<string> {
  // Delegate to the new dynamic gemini model picker
  const tier = estimatedInputTokens > 1000000 ? 'flash' : 'lite';
  return pickGeminiModel(tier, estimatedInputTokens);
}
