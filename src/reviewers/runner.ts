import { GitHubModelFactory, ReviewOptions } from "./factory";

export interface ModelChain {
  primary: string;
  fallbacks: string[];
  max_retries?: number;
}

export interface CompleteOptions {
  messages: Array<{ role: "system" | "user" | "assistant"; content: string }>;
  temperature?: number;
  maxTokens?: number;
}

interface ApiError {
  status?: number;
  message?: string;
}

function _isApiError(err: unknown): err is ApiError {
  return (
    typeof err === "object" &&
    err !== null &&
    ("status" in err || "message" in err)
  );
}

export function normalizeModelId(id: string): string {
  const lowered = id.toLowerCase();
  if (lowered === 'gpt-4o') return 'gpt-4o';
  if (lowered === 'gpt-4o-mini') return 'gpt-4o-mini';
  if (lowered === 'deepseek-r1') return 'DeepSeek-R1';
  if (lowered === 'deepseek-v3') return 'DeepSeek-V3-0324';
  if (lowered === 'llama-3.3-70b-instruct' || lowered === 'llama-3.3-70b') return 'Llama-3.3-70B-Instruct';
  if (lowered === 'phi-4') return 'Phi-4';
  if (lowered === 'phi-4-mini-instruct') return 'Phi-4-mini-instruct';
  if (lowered === 'grok-3' || lowered === 'grok 3') return 'Grok 3';
  return id;
}

function isRecoverableError(err: any): boolean {
  if (typeof err === "object" && err !== null) {
    const status = err.status || err.statusCode || (err.response && err.response.status);
    if (status === 429 || status === 503 || status === 502 || status === 504 || status === 500) {
      return true;
    }
    const message = (err.message || String(err)).toLowerCase();
    if (message.includes("429") || message.includes("503") || message.includes("rate limit") || message.includes("too many requests") || message.includes("server error")) {
      return true;
    }
  }
  return false;
}

function isHardFailure(err: any): boolean {
  if (typeof err === "object" && err !== null) {
    const status = err.status || err.statusCode || (err.response && err.response.status);
    if (status === 400 || status === 401 || status === 403) {
      return true;
    }
    const message = (err.message || String(err)).toLowerCase();
    if (message.includes("400") || message.includes("401") || message.includes("403") || message.includes("unauthorized") || message.includes("invalid key") || message.includes("forbidden")) {
      return true;
    }
  }
  return false;
}

async function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function complete(
  chain: ModelChain,
  options: CompleteOptions
): Promise<{ content: string; modelUsed: string }> {
  const client = GitHubModelFactory.getClient();
  const models = [chain.primary, ...chain.fallbacks];

  for (const rawModel of models) {
    const model = normalizeModelId(rawModel);
    let attempt = 0;
    const maxRetries = chain.max_retries ?? 3;
    let delayMs = 1000;

    while (attempt < maxRetries) {
      try {
        console.log(`[AI Review] Attempting review with model: ${model} (Attempt ${attempt + 1}/${maxRetries})`);

        const response = await client.chat.completions.create({
          model: model,
          messages: options.messages as any,
          temperature: options.temperature ?? 0.2,
          max_tokens: options.maxTokens,
        });

        const content = response.choices[0].message.content || "No review feedback provided.";
        console.log(`[AI Review Success] Request successfully served by model: ${model}`);
        return {
          content,
          modelUsed: model,
        };
      } catch (error) {
        attempt++;

        if (isHardFailure(error)) {
          const errorMsg = error instanceof Error ? error.message : String(error);
          console.error(`[AI Review Error] Hard failure (non-recoverable) encountered for model ${model}: ${errorMsg}`);
          throw error; // hard failures halt immediately without fallbacks!
        }

        if (isRecoverableError(error)) {
          if (attempt < maxRetries) {
            console.warn(`[AI Review Warning] Recoverable error for ${model}: ${error instanceof Error ? error.message : String(error)}. Retrying in ${delayMs}ms...`);
            await delay(delayMs);
            delayMs *= 2;
          } else {
            console.warn(`[AI Review Warning] Usage/Rate limit or server error hit for ${model} and exhausted all ${maxRetries} retries. Rotating to next fallback...`);
          }
        } else {
          // If it's some other non-recoverable and non-hard error, or we are not sure, we can rotate immediately
          const errorMsg = error instanceof Error ? error.message : String(error);
          console.warn(`[AI Review Warning] Model ${model} encountered an unexpected error: ${errorMsg}. Rotating to next fallback...`);
          break; // Rotate to next model in the fallback chain immediately without retrying
        }
      }
    }
  }

  throw new Error("All requested GitHub Model providers and fallbacks failed or exhausted their usage limits.");
}

export async function runReview(options: ReviewOptions): Promise<string> {
  const fallbackChain = GitHubModelFactory.getFallbackChain();
  const primary = fallbackChain[0] || 'gpt-4o-mini';
  const fallbacks = fallbackChain.slice(1);

  const chain: ModelChain = {
    primary,
    fallbacks,
    max_retries: 3
  };

  const messages = [
    {
      role: "system" as const,
      content: `You are an expert automated code review agent. Rules to enforce:\n${options.rules.join("\n")}`
    },
    {
      role: "user" as const,
      // Wrap the prContent in XML tags to establish structural boundaries and prevent prompt injection
      content: `Review the following Pull Request changes:\n\n<pr_content>\n${options.prContent}\n</pr_content>`
    }
  ];

  const result = await complete(chain, {
    messages,
    temperature: 0.2
  });

  return result.content;
}
