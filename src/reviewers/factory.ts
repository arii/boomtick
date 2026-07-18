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

  private static clientInstance: OpenAI | null = null;

  static getClient(): OpenAI {
    if (this.clientInstance) {
      return this.clientInstance;
    }

    const token = process.env.GITHUB_TOKEN;
    if (!token) {
      throw new Error("Missing GITHUB_TOKEN environment variable.");
    }

    // Validate GITHUB_TOKEN format strictly to prevent header injection or malicious token values
    if (!/^[A-Za-z0-9_\-\.]+$/.test(token)) {
      throw new Error("Invalid GITHUB_TOKEN format.");
    }

    this.clientInstance = new OpenAI({
      baseURL: "https://models.inference.ai.azure.com",
      apiKey: token,
    });

    return this.clientInstance;
  }

  // Exposed for testing purposes to reset cached instance
  static resetClient(): void {
    this.clientInstance = null;
  }

  static getFallbackChain(): string[] {
    const target = (process.env.AI_PROVIDER || '').toLowerCase();
    const config = Object.prototype.hasOwnProperty.call(this.MODEL_REGISTRY, target)
      ? this.MODEL_REGISTRY[target]
      : this.MODEL_REGISTRY["gpt-4o-mini"];

    // Return the primary model followed by its dedicated backups
    return [config.modelId, ...config.fallbacks];
  }
}
