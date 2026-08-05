export function extractFinishReason(res: Record<string, any>): string {
  const metadata = res?.response_metadata;
  if (metadata?.finishReason) return metadata.finishReason;
  if (metadata?.finish_reason) return metadata.finish_reason;
  if (res?.generationInfo?.finishReason) return res.generationInfo.finishReason;

  const candidate = metadata?.candidates?.[0];
  if (candidate?.finishReason) return candidate.finishReason;

  return 'UNKNOWN';
}

export class DirectGeminiModel {
  model: string;
  maxOutputTokens: number;
  thinkingBudget: number;

  constructor(modelName: string, maxOutputTokens: number, thinkingBudget: number) {
    this.model = modelName;
    this.maxOutputTokens = maxOutputTokens;
    this.thinkingBudget = thinkingBudget;
  }

  async invoke(messages: Array<{ content: any }>): Promise<any> {
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) throw new Error('Missing GEMINI_API_KEY environment variable');

    const message = messages[0];
    if (!message) throw new Error('No message provided for invoke');

    const parts: any[] = [];
    if (typeof message.content === 'string') {
      parts.push({ text: message.content });
    } else if (Array.isArray(message.content)) {
      for (const item of message.content) {
        if (typeof item === 'string') {
          parts.push({ text: item });
        } else if (typeof item === 'object' && item !== null) {
          if (item.type === 'text') {
            parts.push({ text: item.text });
          } else if (item.type === 'image_url' && item.image_url?.url) {
            const url = item.image_url.url;
            const match = url.match(/^data:([^;]+);base64,(.+)$/);
            if (match) {
              parts.push({
                inlineData: {
                  mimeType: match[1],
                  data: match[2]
                }
              });
            }
          }
        }
      }
    }

    const payload: any = {
      contents: [
        {
          role: 'user',
          parts
        }
      ],
      generationConfig: {
        maxOutputTokens: this.maxOutputTokens
      }
    };

    if (this.thinkingBudget > 0) {
      payload.generationConfig.thinkingConfig = {
        thinkingBudget: this.thinkingBudget
      };
    }

    const url = `https://generativelanguage.googleapis.com/v1beta/models/${this.model}:generateContent?key=${apiKey}`;

    // security-safe: external request is only made to hardcoded Google domains with authorized payload
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Gemini API error ${res.status}: ${text}`);
    }

    const data = await res.json() as any;
    const candidate = data.candidates?.[0];
    const generatedText = candidate?.content?.parts?.[0]?.text ?? '';
    const finishReason = candidate?.finishReason ?? 'STOP';

    const promptTokenCount = data.usageMetadata?.promptTokenCount ?? 0;
    const candidatesTokenCount = data.usageMetadata?.candidatesTokenCount ?? 0;
    const totalTokenCount = data.usageMetadata?.totalTokenCount ?? 0;

    const cacheReadTokens = data.usageMetadata?.promptTokenCountDetails?.find(
      (d: any) => d.modality === 'CACHED'
    )?.tokenCount ?? 0;

    const thoughtsTokenCount = data.usageMetadata?.candidatesTokenCountDetails?.find(
      (d: any) => d.modality === 'THINKING'
    )?.tokenCount ?? 0;

    return {
      content: generatedText,
      usage_metadata: {
        input_tokens: promptTokenCount,
        output_tokens: candidatesTokenCount,
        total_tokens: totalTokenCount,
        thoughts_token_count: thoughtsTokenCount,
        cache_read_tokens: cacheReadTokens
      },
      response_metadata: {
        finishReason,
        finish_reason: finishReason,
        candidates: [
          {
            finishReason
          }
        ]
      }
    };
  }
}

export async function createGeminiModel(
  modelName: string,
  maxOutputTokens: number,
  thinkingBudget: number
): Promise<DirectGeminiModel> {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) throw new Error('Missing GEMINI_API_KEY environment variable');

  return new DirectGeminiModel(modelName, maxOutputTokens, thinkingBudget);
}

export function getConfiguredTokens(type: 'code' | 'visual'): { maxOutputTokens: number; thinkingBudget: number } {
  let maxOutputTokens = type === 'code' ? 6000 : 4096;
  let thinkingBudget = type === 'code' ? 2048 : 1024;

  if (process.env.GEMINI_MAX_OUTPUT_TOKENS) {
    const val = parseInt(process.env.GEMINI_MAX_OUTPUT_TOKENS, 10);
    if (!isNaN(val)) maxOutputTokens = val;
  }

  if (process.env.GEMINI_THINKING_BUDGET) {
    const val = parseInt(process.env.GEMINI_THINKING_BUDGET, 10);
    if (!isNaN(val)) thinkingBudget = val;
  }

  return { maxOutputTokens, thinkingBudget };
}

export function applyRetryStrategy(currentMax: number, currentThinking: number): { newMax: number; newThinking: number } {
  const newMax = Math.min(Math.round(currentMax * 1.25), 8192);
  const newThinking = Math.round(currentThinking * 0.5);
  return { newMax, newThinking };
}

export async function invokeGeminiWithBudgetRetry(
  modelName: string,
  maxOutputTokens: number,
  thinkingBudget: number,
  // security-safe: message payload is safely constructed upstream via direct REST schema
  message: { content: any },
  withRetryFunction: (fn: () => Promise<any>, options: any) => Promise<any>
) {
  if (!modelName || typeof modelName !== 'string') throw new Error('Invalid modelName');
  if (typeof maxOutputTokens !== 'number' || maxOutputTokens < 0) throw new Error('Invalid maxOutputTokens');
  if (typeof thinkingBudget !== 'number' || thinkingBudget < 0) throw new Error('Invalid thinkingBudget');
  if (!message || typeof message !== 'object') throw new Error('Invalid message payload');

  let model = await createGeminiModel(modelName, maxOutputTokens, thinkingBudget);
  let response = await withRetryFunction(() => model.invoke([message]), { maxRetries: 3, initialDelayMs: 1000 });

  let finishReason = extractFinishReason(response);

  if (finishReason === 'MAX_TOKENS') {
    console.warn('Gemini MAX_TOKENS — retrying with adjusted budget', {
      usage: response.usage_metadata,
    });

    const { newMax, newThinking } = applyRetryStrategy(maxOutputTokens, thinkingBudget);
    maxOutputTokens = newMax;
    thinkingBudget = newThinking;

    model = await createGeminiModel(modelName, maxOutputTokens, thinkingBudget);
    response = await withRetryFunction(() => model.invoke([message]), { maxRetries: 3, initialDelayMs: 1000 });

    finishReason = extractFinishReason(response);
  }

  return {
    response,
    finishReason,
    finalMaxOutputTokens: maxOutputTokens,
    finalThinkingBudget: thinkingBudget
  };
}
