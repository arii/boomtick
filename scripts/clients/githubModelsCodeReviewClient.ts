import {
  parseCodeReviewVerdict,
  parseCodeReviewStateDetailed,
  estimateMaxOutputTokens,
  budgetInputContext,
  buildReviewPayload,
  extractFeedbackText,
  calculateEstimatedTokens,
  withRetry
} from '../../lib/codeReviewUtils';
import { buildSystemPrompt } from '../../lib/buildCodeReviewPrompt';
import type { CodeReviewSummary, CodeReviewResult, ModelChain } from '../../lib/codeReviewTypes';
import type { CodeReviewClientStrategy } from '../../lib/codeReviewOrchestrator';
import { getAvailableModels } from '../../lib/modelPicker';
import * as fs from 'fs';
import * as path from 'path';

export interface GitHubModelsResponse {
  usage?: {
    prompt_tokens?: number,
    completion_tokens?: number,
    total_tokens?: number,
    prompt_tokens_details?: { cached_tokens?: number }
  },
  choices?: Array<{ finish_reason?: string, message?: { content?: string } }>
}

async function complete(
  chain: ModelChain,
  messages: any[],
  maxTokens: number
): Promise<{ response: any, modelName: string }> {
  const apiKey = process.env.GITHUB_TOKEN;
  if (!apiKey) throw new Error('Missing GITHUB_TOKEN environment variable');

  // Validate apiKey format to prevent header injection or malicious token values
  if (!/^[A-Za-z0-9_-]+$/.test(apiKey)) {
    throw new Error('Invalid GITHUB_TOKEN format');
  }

  const url = 'https://models.inference.ai.azure.com/chat/completions';
  const modelsToTry = [chain.primary, ...(chain.fallbacks || [])];

  for (const [index, modelName] of modelsToTry.entries()) {
    try {
      const fetchResponse = await withRetry(async () => {
        const response = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${apiKey}`
          },
          body: JSON.stringify({
            model: modelName,
            messages: messages,
            max_tokens: maxTokens,
            temperature: 0.1
          })
        }).catch(e => {
          throw new Error(`Failed to fetch from GitHub Models API: ${e.message || e}`);
        });

        if (!response.ok) {
          // Avoid leaking raw response text or full status text into thrown error messages for security
          console.error(`[GitHub Models API Error] Status: ${response.status}`);
          throw new Error(`GitHub Models API error: ${response.status}`);
        }
        return response;
      }, { maxRetries: Math.min(chain.max_retries ?? 3, 5), initialDelayMs: 1000 });

      const responseJson = await fetchResponse.json() as GitHubModelsResponse;
      console.log(`📌 github-models-code-review successfully served request using model: ${modelName}`);
      return { response: responseJson, modelName };
    } catch (error: any) {
      const errorMsg = error.message || String(error);
      const isRecoverable = errorMsg.includes('429') ||
                            errorMsg.includes('503') ||
                            errorMsg.toLowerCase().includes('rate limit') ||
                            errorMsg.toLowerCase().includes('overloaded') ||
                            errorMsg.toLowerCase().includes('timeout') ||
                            errorMsg.toLowerCase().includes('resource exhausted');

      if (isRecoverable && index < modelsToTry.length - 1) {
        console.warn(`⚠️ Model ${modelName} failed with recoverable error (${errorMsg}). Falling back to next model...`);
        continue;
      }

      throw error; // If hard failure or out of fallbacks, rethrow
    }
  }
  throw new Error('All models in the chain failed.');
}

export const githubModelsCodeReviewClient: CodeReviewClientStrategy = {
  botName: 'github-models-code-review',
  reportTitle: '🐙 GitHub Models Code Review',
  botTagline: 'Powered by GitHub Models',
  reportFileName: 'github-models-code-review.md',

  invokeReview: async (summary: CodeReviewSummary, forceMaxOutputTokens?: number): Promise<CodeReviewResult> => {
    const systemPrompt = buildSystemPrompt(summary);
    const { diffText, externalText } = budgetInputContext(systemPrompt, summary);

    const calculatedTokens = calculateEstimatedTokens([systemPrompt, diffText, externalText || '']);
    const estimatedInputTokens = Math.max(summary.estimatedInputTokens || 0, calculatedTokens);

    let maxTokens = forceMaxOutputTokens ?? estimateMaxOutputTokens(summary, systemPrompt.length, 0);

    const messages = buildReviewPayload(systemPrompt, diffText, externalText);

    if (!messages || !Array.isArray(messages) || messages.length === 0) {
      throw new Error('Failed to build a valid messages payload for the AI client.');
    }

    let chain: ModelChain = {
      primary: "gpt-4o-mini",
      fallbacks: [],
      max_retries: 3
    };

    try {
      const configPath = path.resolve(process.cwd(), 'project_config.json');
      const configData = JSON.parse(fs.readFileSync(configPath, 'utf8'));
      const parsedChain = configData['code-review-chain'];

      if (
        parsedChain &&
        typeof parsedChain === 'object' &&
        typeof parsedChain.primary === 'string' &&
        Array.isArray(parsedChain.fallbacks) &&
        parsedChain.fallbacks.every((f: any) => typeof f === 'string') &&
        typeof parsedChain.max_retries === 'number'
      ) {
        chain = parsedChain as ModelChain;
      } else if (parsedChain) {
        console.warn("⚠️ Invalid model chain config schema in project_config.json, using defaults.");
      }
    } catch (e) {
      console.warn("⚠️ Could not load model chain config, using defaults.");
    }

    // Attempt to pick optimal if the primary isn't hardcoded in project_config? Or let the chain logic override it.
    // The prompt says "Treat your model list as dynamic configuration", so we'll just use the chain.
    const apiKey = process.env.GITHUB_TOKEN;
    if (apiKey) {
      try {
        const models = await getAvailableModels(apiKey);
        const matchedModel = models.find(m => m.id === chain.primary || m.id.includes(chain.primary));
        if (matchedModel?.limits?.max_output_tokens) {
          maxTokens = Math.min(maxTokens, matchedModel.limits.max_output_tokens);
        }
      } catch (err) {
        // ignore
      }
    }

    const { response, modelName } = await complete(chain, messages, maxTokens);

    const usageMetadata = (response as GitHubModelsResponse).usage;
    const inputTokens = usageMetadata?.prompt_tokens ?? 0;
    const outputTokens = usageMetadata?.completion_tokens ?? 0;
    const totalTokens = usageMetadata?.total_tokens ?? 0;
    const cacheTokens = usageMetadata?.prompt_tokens_details?.cached_tokens ?? 0;
    const cost = 0;

    const firstChoice = response.choices && response.choices[0];
    const finishReason = firstChoice?.finish_reason;
    const isTruncated = finishReason === 'length';
    if (isTruncated) {
      console.warn(`⚠️  github-models-code-review output truncated (finish_reason: length, tokens: ${totalTokens}).`);
    }

    const rawContent = firstChoice?.message?.content || '';
    const feedback = extractFeedbackText(rawContent);

    const parsedState = parseCodeReviewStateDetailed(feedback);

    return {
      feedback: feedback,
      role: summary.role,
      tokens: totalTokens,
      inputTokens,
      outputTokens,
      cacheTokens,
      cost: cost,
      llmVerdict: parseCodeReviewVerdict(feedback),
      state: parsedState.state,
      modelName: modelName,
      truncated: isTruncated,
      parseError: parsedState.parseError,
    };
  }
};
