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
import type { CodeReviewSummary, CodeReviewResult } from '../../lib/codeReviewTypes';
import type { CodeReviewClientStrategy } from '../../lib/codeReviewOrchestrator';
import { pickOptimalModel, getAvailableModels } from '../../lib/modelPicker';

async function createModelConfig(
  estimatedInputTokens: number = 0,
  maxOutputTokens: number = 1500
): Promise<{ modelName: string, maxTokens: number }> {
  const apiKey = process.env.GITHUB_TOKEN;
  if (!apiKey) throw new Error('Missing GITHUB_TOKEN environment variable');

  const fallback = process.env.GITHUB_MODELS_MODEL || 'gpt-4o-mini';
  const modelName = await pickOptimalModel(apiKey, fallback, false, estimatedInputTokens);

  let finalMaxTokens = maxOutputTokens;
  try {
    const models = await getAvailableModels(apiKey);
    const matchedModel = models.find(m => m.id === modelName || m.id.includes(modelName));
    if (matchedModel?.limits?.max_output_tokens) {
      finalMaxTokens = Math.min(finalMaxTokens, matchedModel.limits.max_output_tokens);
    }
  } catch (err) {
    console.warn('⚠️ Could not check model limits from catalog, falling back to budgeted tokens:', err);
  }

  console.log(`📌 github-models-code-review using model: ${modelName}, maxOutputTokens: ${finalMaxTokens}`);

  return { modelName, maxTokens: finalMaxTokens };
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

    const maxOutputTokens = forceMaxOutputTokens ?? estimateMaxOutputTokens(summary, systemPrompt.length, 0);
    const { modelName, maxTokens } = await createModelConfig(estimatedInputTokens, maxOutputTokens);

    const messages = buildReviewPayload(systemPrompt, diffText, externalText);

    if (!messages || !Array.isArray(messages) || messages.length === 0) {
      throw new Error('Failed to build a valid messages payload for the AI client.');
    }

    const apiKey = process.env.GITHUB_TOKEN;
    const url = 'https://models.inference.ai.azure.com/chat/completions';

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
        throw new Error(`Failed to fetch from GitHub Models API: ${e}`, { cause: e });
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`GitHub Models API error: ${response.status} ${response.statusText} - ${errText}`);
      }
      return response;
    }, { maxRetries: 3, initialDelayMs: 1000 });

    const response = await fetchResponse.json() as {
      usage?: {
        prompt_tokens?: number,
        completion_tokens?: number,
        total_tokens?: number,
        prompt_tokens_details?: { cached_tokens?: number }
      },
      choices?: Array<{ finish_reason?: string, message?: { content?: string } }>
    };

    const usageMetadata = response.usage;
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
