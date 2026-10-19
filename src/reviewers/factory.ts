import { OpenAI } from "openai";

export interface ReviewOptions {
  prContent: string;
  rules: string[];
}


export class GitHubModelFactory {
  private static clientInstance: OpenAI | null = null;

  static getClient(): OpenAI {
    if (this.clientInstance) {
      return this.clientInstance;
    }

    const openaiKey = process.env.OPENAI_API_KEY || process.env.OPEN_API_KEY;
    const githubToken = process.env.GITHUB_TOKEN;

    const token = openaiKey || githubToken;
    if (!token) {
      throw new Error("Missing GITHUB_TOKEN environment variable.");
    }

    // Validate GITHUB_TOKEN format strictly to prevent header injection or malicious token values
    if (!/^[A-Za-z0-9_\-\.]+$/.test(token)) {
      throw new Error("Invalid GITHUB_TOKEN format.");
    }

    const baseURL = openaiKey ? "https://api.openai.com/v1" : "https://models.inference.ai.azure.com";

    this.clientInstance = new OpenAI({
      baseURL,
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

    return ["gpt-4o-mini"];
  }
}
