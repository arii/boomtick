export interface GeminiModel {
  id: string;
  name: string;
  tier: 'pro' | 'flash' | 'lite';
  maxInputTokens: number;
  maxOutputTokens: number;
}

export const GEMINI_MODELS_METADATA: GeminiModel[] = [
  {
    id: 'gemini-3.1-pro-preview',
    name: 'Gemini 3.1 Pro (Preview)',
    tier: 'pro',
    maxInputTokens: 2000000,
    maxOutputTokens: 8192
  },
  {
    id: 'gemini-3.5-flash',
    name: 'Gemini 3.5 Flash',
    tier: 'flash',
    maxInputTokens: 1000000,
    maxOutputTokens: 8192
  },
  {
    id: 'gemini-3.1-flash-lite',
    name: 'Gemini 3.1 Flash Lite',
    tier: 'lite',
    maxInputTokens: 1000000,
    maxOutputTokens: 8192
  },
  {
    id: 'gemini-2.5-flash',
    name: 'Gemini 2.5 Flash',
    tier: 'flash',
    maxInputTokens: 1000000,
    maxOutputTokens: 8192
  },
  {
    id: 'gemini-2.5-flash-lite',
    name: 'Gemini 2.5 Flash Lite',
    tier: 'lite',
    maxInputTokens: 1000000,
    maxOutputTokens: 8192
  }
];

export const DEPRECATED_MODELS = [
  'gemini-1.5-flash',
  'gemini-1.5-pro',
  'gemini-pro',
  'gemini-2.0-flash',
  'gemini-2.0-pro',
  'gemini-2.0-flash-thinking'
];

let cachedModels: string[] | null = null;

/**
 * Fetches available Gemini models from the API.
 */
export async function resolveAvailableGeminiModels(): Promise<string[]> {
  if (cachedModels) return cachedModels;

  const apiKey = process.env.GEMINI_API_KEY || process.env.JULES_API_KEY;
  if (!apiKey) {
    console.warn("⚠️ No API key found for Gemini model resolution.");
    return [];
  }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s timeout

    const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models?key=${apiKey}`, {
      signal: controller.signal
    });
    clearTimeout(timeoutId);

    if (!res.ok) {
      console.warn(`⚠️ Failed to fetch Gemini models: ${res.status} ${res.statusText}`);
      return [];
    }

    const data = await res.json() as { models?: { name: string }[] };
    if (!data || !Array.isArray(data.models)) {
      console.warn("⚠️ Invalid format returned from Gemini models endpoint.");
      return [];
    }

    cachedModels = data.models.map(m => m.name.replace('models/', ''));
    return cachedModels;
  } catch (error) {
    console.warn(`⚠️ Error resolving available Gemini models: ${error}`);
    return [];
  }
}

/**
 * Selects an optimal Gemini model based on the requested tier.
 * Explicitly avoids deprecated models and prioritizes the Gemini 3.x suite.
 */
export async function pickGeminiModel(
  preferredTier: 'pro' | 'flash' | 'lite' = 'lite',
  estimatedInputTokens: number = 0
): Promise<string> {
  if (process.env.GEMINI_MODEL) return process.env.GEMINI_MODEL;

  const availableIds = await resolveAvailableGeminiModels();
  const activeModels = GEMINI_MODELS_METADATA.filter(m =>
    availableIds.includes(m.id) && !DEPRECATED_MODELS.includes(m.id)
  );

  if (activeModels.length === 0) {
    return availableIds.find(id => id.includes('3.1') || id.includes('3.5')) ||
           GEMINI_MODELS_METADATA.find(m => m.tier === preferredTier)?.id ||
           GEMINI_MODELS_METADATA[1].id;
  }

  let selected = activeModels.find(m => m.tier === preferredTier) ||
                 activeModels.find(m => m.tier === 'lite') ||
                 activeModels[0];

  if (estimatedInputTokens > selected.maxInputTokens) {
    selected = activeModels.find(m => m.maxInputTokens >= estimatedInputTokens) || selected;
  }

  return selected.id;
}

/**
 * Returns the pricing per 1 million tokens for the given Gemini model.
 * Values are based on Gemini 3.x estimates.
 */
export function getGeminiPricing(modelId: string): { inputCostPerM: number; outputCostPerM: number } {
  if (modelId.includes('gemini-3.5-flash')) {
    return { inputCostPerM: 1.50, outputCostPerM: 9.00 };
  }
  if (modelId.includes('gemini-3.1-flash-lite')) {
    return { inputCostPerM: 0.25, outputCostPerM: 1.50 };
  }
  if (modelId.includes('gemini-2.5-flash-lite')) {
    return { inputCostPerM: 0.10, outputCostPerM: 0.40 };
  }
  if (modelId.includes('gemini-2.5-flash')) {
    return { inputCostPerM: 0.30, outputCostPerM: 2.50 };
  }
  if (modelId.includes('pro')) {
    return { inputCostPerM: 2.00, outputCostPerM: 12.00 };
  }
  // Default fallback
  return { inputCostPerM: 0.10, outputCostPerM: 0.40 };
}
