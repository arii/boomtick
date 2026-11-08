import modelsData from '../data/gemini-models.json';

interface GeminiModelEntry {
  id: string;
  name: string;
  tier: 'pro' | 'flash' | 'lite';
  maxInputTokens: number;
  maxOutputTokens: number;
  inputCostPerM: number;
  outputCostPerM: number;
  reviewAfter: string | null;
  deprecatedAfter: string | null;
}

const GEMINI_MODELS_METADATA: GeminiModelEntry[] = modelsData.models as GeminiModelEntry[];
const DEPRECATED_MODELS: string[] = (modelsData.deprecated as { id: string }[]).map((entry) => entry.id);

// Surface catalog rot as a build signal instead of a runtime surprise.
for (const model of GEMINI_MODELS_METADATA) {
  if (model.reviewAfter && Date.now() > Date.parse(model.reviewAfter)) {
    console.warn(`⚠️ Gemini model catalog entry is stale: ${model.id} (review date ${model.reviewAfter}). Refresh data/gemini-models.json.`);
  }
  if (model.deprecatedAfter && Date.now() > Date.parse(model.deprecatedAfter)) {
    console.warn(`⚠️ Gemini model is past its deprecation date: ${model.id} (${model.deprecatedAfter}).`);
  }
}

let cachedModels: string[] | null = null;

/**
 * Fetches available Gemini models from the API.
 */
async function resolveAvailableGeminiModels(): Promise<string[]> {
  if (cachedModels) return cachedModels;

  const apiKey = process.env.GEMINI_API_KEY;
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
 * Values come from data/gemini-models.json; unknown ids use its default.
 */
export function getGeminiPricing(modelId: string): { inputCostPerM: number; outputCostPerM: number } {
  const entry = GEMINI_MODELS_METADATA.find((model) => model.id === modelId);
  if (entry) {
    return { inputCostPerM: entry.inputCostPerM, outputCostPerM: entry.outputCostPerM };
  }
  return { ...modelsData.defaultPricing };
}
