import { HumanMessage } from '@langchain/core/messages';
import { buildVisualReviewPayload, parseLLMVerdict, parseVisualReviewFindings } from '../../boomtick-pkg/lib/visualReviewUtils';
import { extractFeedbackText } from '../../boomtick-pkg/lib/codeReviewUtils';
import { pickGeminiModel, getGeminiPricing } from '../../boomtick-pkg/lib/geminiModelPicker';
import { extractFinishReason, createGeminiModel, applyRetryStrategy } from '../../boomtick-pkg/lib/geminiUtils';
import type { LLMClientStrategy, AgentRole } from '../../boomtick-pkg/lib/visualReviewOrchestrator';

import type { RouteReview, VisualRouteSummary } from '../../boomtick-pkg/lib/visualReviewTypes';

const ROLE_PROMPTS: Record<AgentRole, string> = {
  CODE_REVIEW: "You are a Senior Software Engineer. Focus on the impact of code changes on the rendered output. Verify that the DOM diff aligns with the visual changes.",
  ACCESSIBILITY: "You are an Accessibility Specialist. Audit the page for contrast issues, tap target sizes, and semantic structure regressions.",
  UX: "You are a Senior UX Researcher. Evaluate the visual hierarchy, information density, and overall user experience. Flag any 'BoomTick' design system violations.",
  VISUAL_REGRESSION: "You are a QA Engineer specialized in visual testing. Look for unintended pixel-perfect shifts, clipping, and color regressions.",
  RESPONSIVE_LAYOUT: "You are a Mobile-First Designer. Specifically audit how the layout collapses across viewports. Flag any horizontal compression or broken grids."
};

export const geminiVisualReviewClient: LLMClientStrategy = {
  botName: 'impact-gemini-review',
  reportTitle: '👁️ Visual Review Agent',
  botTagline: 'Powered by Gemini 3.x Vision + Blast-Radius Analyzer',
  reportFileName: 'gemini-review.md',

  invokeReview: async (summary: VisualRouteSummary, role: AgentRole = 'UX'): Promise<RouteReview> => {
    let modelName: string;
    const estimatedInputTokens = summary.tokens ?? 0;
    try {
      modelName = await pickGeminiModel('lite', estimatedInputTokens);
    } catch (err) {
      console.error('Failed to pick Gemini model, falling back based on input tokens:', err);
      modelName = estimatedInputTokens > 1000000 ? 'gemini-2.5-flash' : 'gemini-2.5-flash-lite';
    }

    let maxOutputTokens = 4096;
    let thinkingBudget = 1024;
    let model = createGeminiModel(modelName, maxOutputTokens, thinkingBudget);
    const baseContent = buildVisualReviewPayload(summary);

    baseContent.push({
      type: 'text',
      text: `YOUR SPECIFIC ROLE FOR THIS REVIEW: ${role}\n${ROLE_PROMPTS[role]}`
    });

    if (summary.previousFindings && summary.previousFindings.length > 0) {
      const findingsStr = summary.previousFindings
        .map(f => {
          let line = `- [${f.id}] ${f.issue} (Status: ${f.status})`;
          if (f.fixSummary) {
            line += `\n   → ${f.fixSummary}`;
          }
          return line;
        })
        .join('\n');

      baseContent.push({
        type: 'text',
        text: `PREVIOUS REVIEW ROUND FINDINGS FOR THIS ROUTE:
${findingsStr}

Your job:
- Confirm THIS issue is resolved before raising anything new.
- Only raise a NEW issue if it is unrelated to anything already addressed, or if the fix for a previous issue introduced a new problem.
- Do not re-open a resolved issue under a different framing.`
      });
    }

    baseContent.push({
      type: 'text',
      text: `You MUST also provide a structured JSON summary of the findings (both old and new) for this route at the end of your response, inside a <findings> tag:
<findings>
{
  "findings": [
    {
      "id": "finding-1",
      "route": "${summary.route}",
      "issue": "Brief description of the issue",
      "status": "resolved",
      "fixSummary": "Brief summary of how it was addressed"
    }
  ]
}
</findings>`
    });

    const message = new HumanMessage({ content: baseContent });
    let response = await model.invoke([message]);

    let finishReason = extractFinishReason(response);

    if (finishReason === 'MAX_TOKENS') {
      console.warn('Gemini MAX_TOKENS — retrying with adjusted budget', {
        usage: response.usage_metadata,
      });

      const { newMax, newThinking } = applyRetryStrategy(maxOutputTokens, thinkingBudget);
      maxOutputTokens = newMax;
      thinkingBudget = newThinking;

      model = createGeminiModel(modelName, maxOutputTokens, thinkingBudget);
      response = await model.invoke([message]);

      finishReason = extractFinishReason(response);
    }

    const usageMetadata = response.usage_metadata as {
      input_tokens?: number;
      output_tokens?: number;
      total_tokens?: number;
      thoughts_token_count?: number;
    };
    const inputTokens = usageMetadata?.input_tokens ?? 0;
    const outputTokens = usageMetadata?.output_tokens ?? 0;
    const totalTokens = usageMetadata?.total_tokens ?? 0;
    const cacheTokens = (usageMetadata as { cache_read_tokens?: number })?.cache_read_tokens ?? 0;
    const thoughtsTokenCount = usageMetadata?.thoughts_token_count ??
                               (typeof response.response_metadata === 'object' && response.response_metadata !== null
                                 ? ((response.response_metadata as Record<string, unknown>).usage as Record<string, unknown>)?.thoughts_token_count as number | undefined
                                 : 0) ?? 0;

    if (thoughtsTokenCount > thinkingBudget * 1.1) {
      console.warn('Thinking budget exceeded by >10%', {
        budgetSet: thinkingBudget,
        thoughtsUsed: thoughtsTokenCount,
        model: modelName,
      });
    }

    const isTruncated = finishReason === 'MAX_TOKENS' || finishReason === 'length' || finishReason === 'max_tokens';

    if (isTruncated) {
      console.error('Gemini truncation', {
        finishReason,
        usage: usageMetadata,
      });
      return {
        route: summary.route,
        severity: summary.severity,
        differencePercent: summary.differencePercent,
        feedback: `Error: Gemini model was truncated during execution (finishReason=${finishReason}).`,
        tokens: totalTokens,
        cost: 0,
        modelName,
        llmVerdict: 'warn',
        findings: [],
        truncated: true,
      };
    }

    const pricing = getGeminiPricing(modelName);
    const cost = pricing ? (inputTokens / 1_000_000) * pricing.inputCostPerM + (outputTokens / 1_000_000) * pricing.outputCostPerM : 0;

    const feedback = extractFeedbackText(response.content) || (
      typeof response.content === 'string' ? response.content : JSON.stringify(response.content)
    );

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
      truncated: isTruncated,
    };
  }
};
