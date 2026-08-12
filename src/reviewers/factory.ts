import { OpenAI } from "openai";

export interface ReviewOptions {
  prContent: string;
  rules: string[];
}

export interface ModelConfiguration {
  modelId: string;
  fallbacks: string[]; // Ordered list of backups if this model hits limits
}

import { loadProjectConfig } from "../../lib/projectConfig";

export class GitHubModelFactory {
  private static clientInstance: OpenAI | null = null;

  static getClient(): OpenAI {
    if (this.clientInstance) {
      return this.clientInstance;
    }

    const token = process.env.OPENAI_API_KEY || process.env.OPEN_API_KEY || process.env.GITHUB_TOKEN;
    if (!token) {
      throw new Error("Missing GITHUB_TOKEN environment variable.");
    }

    // Validate GITHUB_TOKEN format strictly to prevent header injection or malicious token values
    if (!/^[A-Za-z0-9_\-\.]+$/.test(token)) {
      throw new Error("Invalid GITHUB_TOKEN format.");
    }

    this.clientInstance = new OpenAI({
      baseURL: "https://api.openai.com/v1",
      apiKey: token,
    });

    return this.clientInstance;
  }

  // Exposed for testing purposes to reset cached instance
  static resetClient(): void {
    this.clientInstance = null;
  }

  static getFallbackChain(): string[] {
    // 1. Check environment variables
    const primaryEnv = process.env.AI_CHAIN_PRIMARY;
    const fallbacksEnv = process.env.AI_CHAIN_FALLBACKS;
    if (primaryEnv) {
      const fallbacks = fallbacksEnv ? fallbacksEnv.split(',').map(s => s.trim()) : [];
      return [primaryEnv, ...fallbacks];
    }

    // 2. Check AI_PROVIDER environment variable first for testing / legacy compatibility
    const target = (process.env.AI_PROVIDER || '').toLowerCase();
    if (target) {
      const defaultRegistry: Record<string, string[]> = {
        "grok-3": ["Grok 3", "gpt-4o", "gpt-4o-mini"],
        "phi-4": ["Phi-4", "gpt-4o-mini", "Phi-4-mini-instruct"],
        "deepseek": ["DeepSeek-R1", "gpt-4o-mini", "Phi-4"],
        "gpt-4o-mini": ["gpt-4o-mini", "Phi-4-mini-instruct"],
        "gpt-4": ["gpt-4o", "gpt-4o-mini", "Phi-4"],
        "claude": ["claude-3-5-sonnet", "gpt-4o-mini", "Phi-4"]
      };

      if (Object.prototype.hasOwnProperty.call(defaultRegistry, target)) {
        return defaultRegistry[target];
      }
    }

    // 3. Check project config (only if not running in vitest tests to prevent local config from interfering with unit tests)
    if (!process.env.VITEST) {
      try {
        const projConfig = loadProjectConfig();
        if (projConfig.code_review_chain) {
          return [projConfig.code_review_chain.primary, ...projConfig.code_review_chain.fallbacks];
        }
      } catch {
        // ignore
      }
    }

    return ["gpt-4o-mini", "Phi-4-mini-instruct"];
  }
}
