import { buildVisualReviewPayload, parseLLMVerdict, parseVisualReviewFindings } from '../../lib/visualReviewUtils';
import { extractFeedbackText } from '../../lib/codeReviewUtils';
import { pickGeminiModel, getGeminiPricing } from '../../lib/geminiModelPicker';
import { extractFinishReason, createGeminiModel, applyRetryStrategy } from '../../lib/geminiUtils';
import { invokeGeminiModelWithRetry } from '../../lib/geminiClientUtils';
import { invokeGeminiModelWithRetry } from '../../lib/geminiClientUtils';
import { invokeGeminiModelWithRetry } from '../../lib/geminiClientUtils';
import { addPreviousFindingsToPayload, formatVisualResponse } from '../../lib/geminiClientUtils';
import { invokeGeminiModelWithRetry } from '../../lib/geminiClientUtils';
import type { LLMClientStrategy, AgentRole } from '../../lib/visualReviewOrchestrator';

import type { RouteReview, VisualRouteSummary } from '../../lib/visualReviewTypes';

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
        const {
      finishReason,
      usageMetadata,
      inputTokens,
      outputTokens,
      totalTokens,
      cacheTokens,
      isTruncated,
      cost,
      feedback
    } = await invokeGeminiModelWithRetry(modelName, maxOutputTokens, thinkingBudget, message);

    if (isTruncated) {
      console.error('Gemini truncation', {
        finishReason,
        usage: usageMetadata,
      });
      // Do not throw here, instead pass the error state gracefully
      // so it can be handled by orchestrator without breaking the CI suite
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
