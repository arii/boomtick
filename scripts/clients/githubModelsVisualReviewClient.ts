import { addPreviousFindingsToPayload, formatVisualResponse } from '../../lib/geminiClientUtils';
import * as fs from 'fs';
import * as path from 'path';
import { buildVisualReviewPayload, parseLLMVerdict, parseVisualReviewFindings } from '../../lib/visualReviewUtils';
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

async function createModelConfig(estimatedInputTokens: number = 0): Promise<{ apiKey: string; modelName: string; maxTokens: number }> {
  const apiKey = process.env.GITHUB_TOKEN;
  if (!apiKey) throw new Error('Missing GITHUB_TOKEN environment variable');

  const fallback = process.env.GITHUB_MODELS_MODEL || 'gpt-4o-mini';
  const modelName = await pickOptimalModel(apiKey, fallback, true, estimatedInputTokens);

  return { apiKey, modelName, maxTokens: 1024 };
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

    const { apiKey, modelName, maxTokens } = await createModelConfig(estimatedInputTokens);
    const baseContent = buildVisualReviewPayload(summary);

    addPreviousFindingsToPayload(summary, baseContent);



    baseContent.push({
      type: 'text',
      text: `You MUST also provide a structured JSON summary of the findings (both old and new) for this route at the end of your response, inside a <findings> tag:\n<findings>\n{\n  "findings": [\n    {\n      "id": "finding-1",\n      "route": "${summary.route}",\n      "issue": "Brief description of the issue",\n      "status": "resolved",\n      "fixSummary": "Brief summary of how it was addressed"\n    }\n  ]\n}\n</findings>`
    });

    let response;
    try {
      response = await fetch('https://models.inference.ai.azure.com/chat/completions', {
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

    return parseVisualReviewReturn(summary, feedback, totalTokens, inputTokens, outputTokens, cacheTokens, cost, modelName, false);
  }
};
