import { ProviderTier } from "../errors.js";

/** Default local structured-output model, per the runtime research (art_7FsLzVOd §2). */
export const DEFAULT_LOCAL_STRUCTURED_MODEL = "gemma3:4b";
/** Default local tool-calling model, per the runtime research (art_7FsLzVOd §2). */
export const DEFAULT_LOCAL_TOOL_MODEL = "phi4-mini";
/** All model calls run at temperature 0 — small models degrade sharply above it. */
export const WORKFLOW_TEMPERATURE = 0;
/**
 * Deliberately raised from Ollama's 4,096 default. RAM budget: 16K ctx on a
 * 4B q4 model needs roughly 6–8 GiB total; raising further multiplies KV-cache
 * memory. Workflows plan around 8–16K usable tokens, not the advertised 128K.
 */
export const LOCAL_NUM_CTX = 16384;

export const OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1";
/** Current endpoint per the Nebius cookbook (October 2026). */
export const NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1";

export interface ProviderEnvConfig {
  ollamaBaseUrl: string;
  localStructuredModel: string;
  localToolModel: string;
  openRouterApiKey?: string;
  openRouterModel?: string;
  nebiusApiKey?: string;
  nebiusModel?: string;
}

export function readProviderEnv(env: Record<string, string | undefined> = process.env): ProviderEnvConfig {
  const config: ProviderEnvConfig = {
    ollamaBaseUrl: env.OLLAMA_BASE_URL ?? "http://127.0.0.1:11434",
    localStructuredModel: env.WORKFLOW_LOCAL_STRUCTURED_MODEL ?? DEFAULT_LOCAL_STRUCTURED_MODEL,
    localToolModel: env.WORKFLOW_LOCAL_TOOL_MODEL ?? DEFAULT_LOCAL_TOOL_MODEL,
    openRouterApiKey: env.OPENROUTER_API_KEY || undefined,
    openRouterModel: env.OPENROUTER_MODEL || undefined,
    nebiusApiKey: env.NEBIUS_API_KEY || undefined,
    nebiusModel: env.NEBIUS_MODEL || undefined,
  };

  // Pin a specific model per account, never the random `openrouter/free`
  // router — unpinned routing picks models at random and breaks schema
  // behavior predictability (research art_7FsLzVOd §3).
  if (config.openRouterApiKey && !config.openRouterModel) {
    throw new Error(
      "OPENROUTER_API_KEY is set but OPENROUTER_MODEL is not. Pin a specific model (e.g. a :free model your account has access to); do not rely on the random free router.",
    );
  }
  if (config.nebiusApiKey && !config.nebiusModel) {
    throw new Error("NEBIUS_API_KEY is set but NEBIUS_MODEL is not. Pin a specific Nebius model id.");
  }
  return config;
}

/** Which tiers are configured; used for the local-only degradation error. */
export function configuredTiers(config: ProviderEnvConfig): ProviderTier[] {
  const tiers: ProviderTier[] = ["local"];
  if (config.openRouterApiKey && config.openRouterModel) tiers.push("openrouter");
  if (config.nebiusApiKey && config.nebiusModel) tiers.push("nebius");
  return tiers;
}
