import * as fs from 'fs';
import * as path from 'path';
import { buildVisualReviewPayload, enrichVisualReviewPayload, parseLLMVerdict, parseVisualReviewFindings } from '../../lib/visualReviewUtils';
import { extractFeedbackText } from '../../lib/codeReviewUtils';
import type { LLMClientStrategy } from '../../lib/visualReviewOrchestrator';
import type { RouteReview, VisualRouteSummary } from '../../lib/visualReviewTypes';
import { pickOptimalModel } from '../../lib/modelPicker';
import { DOM_REVIEW_DIR } from '../../lib/visualReviewConstants';

class VisualReviewError extends Error {
  cause?: unknown;
  constructor(message: string, options?: { cause?: unknown }) {
    super(message);
    this.name = 'VisualReviewError';
    if (options && 'cause' in options) {
      this.cause = options.cause;
    }
  }
}

async function createModelConfig(estimatedInputTokens: number = 0): Promise<{ apiKey: string; modelName: string; maxTokens: number; baseURL: string }> {
  const openaiKey = process.env.OPENAI_API_KEY || process.env.OPEN_API_KEY;
  const githubToken = process.env.GITHUB_TOKEN;

  const apiKey = openaiKey || githubToken;
  if (!apiKey) throw new Error('Missing GITHUB_TOKEN, OPENAI_API_KEY, or OPEN_API_KEY environment variable');

  const baseURL = openaiKey ? 'https://api.openai.com/v1/chat/completions' : 'https://models.inference.ai.azure.com/chat/completions';

  const fallback = process.env.GITHUB_MODELS_MODEL || 'gpt-4o-mini';
  const modelName = await pickOptimalModel(apiKey, fallback, true, estimatedInputTokens);

  return { apiKey, modelName, maxTokens: 1024, baseURL };
}

export const githubModelsVisualReviewClient: LLMClientStrategy = {
  botName: 'impact-github-models-review',
  reportTitle: '🐙 GitHub Models Visual Review',
  botTagline: 'Powered by GitHub Models Vision + Blast-Radius Analyzer',
  reportFileName: 'github-models-review.md',

  invokeReview: async (summary: VisualRouteSummary): Promise<RouteReview> => {
    const domDiffPath = path.join(DOM_REVIEW_DIR, summary.slug, 'diff.txt');
    let domDiffLength = 0;
    if (fs.existsSync(domDiffPath)) {
      const content = fs.readFileSync(domDiffPath, 'utf8');
      domDiffLength = Math.min(content.length, 3000);
    }
    const estimatedInputTokens = Math.ceil(domDiffLength / 4);

    const { apiKey, modelName, maxTokens, baseURL } = await createModelConfig(estimatedInputTokens);
    const baseContent = buildVisualReviewPayload(summary);

    enrichVisualReviewPayload(baseContent, summary);

    let response;
    try {
      response = await fetch(baseURL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`
        },
        body: JSON.stringify({
          model: modelName,
          messages: [{ role: 'user', content: baseContent }],
          max_tokens: maxTokens,
          temperature: 0.1
        })
      });
    } catch (err) {
      throw new VisualReviewError(`Network or fetch error during GitHub Models Visual Review: ${err instanceof Error ? err.message : String(err)}`, { cause: err });
    }

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`GitHub Models API error: ${response.status} ${response.statusText} - ${errorText}`);
    }

    const data = await response.json();
    const usageMetadata = data.usage;
    const inputTokens = usageMetadata?.input_tokens ?? usageMetadata?.prompt_tokens ?? 0;
    const outputTokens = usageMetadata?.output_tokens ?? usageMetadata?.completion_tokens ?? 0;
    const totalTokens = usageMetadata?.total_tokens ?? 0;
    const cacheTokens = usageMetadata?.cache_read_tokens ?? usageMetadata?.prompt_tokens_details?.cached_tokens ?? 0;

    const cost = 0;

    const firstChoice = data.choices && data.choices[0];
    const rawContent = firstChoice?.message?.content || '';
    const feedback = extractFeedbackText(rawContent);

    return {
      route: summary.route,
      severity: summary.severity,
      differencePercent: summary.differencePercent,
      feedback: feedback,
      tokens: totalTokens,
      inputTokens,
      outputTokens,
      cacheTokens,
      cost: cost,
      modelName: modelName,
      llmVerdict: parseLLMVerdict(feedback),
      findings: parseVisualReviewFindings(feedback),
    };
  }
};
