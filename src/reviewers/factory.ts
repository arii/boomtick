import { OpenAI } from "openai";

export interface ReviewOptions {
  prContent: string;
  rules: string[];
}

export interface ModelConfiguration {
  modelId: string;
  fallbacks: string[]; // Ordered list of backups if this model hits limits
}

export class GitHubModelFactory {
  private static readonly MODEL_REGISTRY: Record<string, ModelConfiguration> = {
    "grok-3": {
      modelId: "Grok 3",
      fallbacks: ["gpt-4o", "gpt-4o-mini"]
    },
    "phi-4": {
      modelId: "Phi-4",
      fallbacks: ["gpt-4o-mini", "Phi-4-mini-instruct"]
    },
    "deepseek": {
      modelId: "DeepSeek-R1",
      fallbacks: ["gpt-4o-mini", "Phi-4"]
    },
    "gpt-4o-mini": {
      modelId: "gpt-4o-mini",
      fallbacks: ["Phi-4-mini-instruct"]
    },
    "gpt-4": {
      modelId: "gpt-4o",
      fallbacks: ["gpt-4o-mini", "Phi-4"]
    },
    "claude": {
      modelId: "claude-3-5-sonnet",
      fallbacks: ["gpt-4o-mini", "Phi-4"]
    }
  };

  static getClient(): OpenAI {
    const token = process.env.GITHUB_TOKEN;
    if (!token) throw new Error("Missing GITHUB_TOKEN environment variable.");

    return new OpenAI({
      baseURL: "https://models.inference.ai.azure.com",
      apiKey: token,
    });
  }

  static getFallbackChain(): string[] {
    const target = process.env.AI_PROVIDER?.toLowerCase() || "gpt-4o-mini";
    const config = this.MODEL_REGISTRY[target] || this.MODEL_REGISTRY["gpt-4o-mini"];

    // Return the primary model followed by its dedicated backups
    return [config.modelId, ...config.fallbacks];
  }
}
