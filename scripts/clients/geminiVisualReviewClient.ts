import { buildVisualReviewPayload, parseLLMVerdict, parseVisualReviewFindings } from '../../lib/visualReviewUtils';
import { extractFeedbackText } from '../../lib/codeReviewUtils';
import { pickGeminiModel, getGeminiPricing } from '../../lib/geminiModelPicker';
import { extractFinishReason, createGeminiModel, applyRetryStrategy } from '../../lib/geminiUtils';
import { addPreviousFindingsToPayload, formatVisualResponse, invokeGeminiModelWithRetry, handleTruncation, parseVisualReviewReturn } from '../../lib/geminiClientUtils';
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
    const baseContent = buildVisualReviewPayload(summary);
    baseContent.push({
      type: 'text',
      text: `YOUR SPECIFIC ROLE FOR THIS REVIEW: ${role}\n${ROLE_PROMPTS[role]}`
    });
    addPreviousFindingsToPayload(summary, baseContent);
    baseContent.push({
      type: 'text',
      text: `You MUST also provide a structured JSON summary of the findings (both old and new) for this route at the end of your response, inside a <findings> tag:\n<findings>\n{\n  "verdict": "fail" | "pass" | "warn",\n  "findings": [ { "id": "V-001", "issue": "description", "status": "resolved" | "unresolved", "severity": "high" | "low" | "info" } ]\n}\n</findings>`
    });

    const { HumanMessage } = await import('@langchain/core/messages');
    const message = new HumanMessage({ content: baseContent });

    const reviewPayload = await invokeGeminiModelWithRetry(modelName, maxOutputTokens, thinkingBudget, message);
    const { finishReason, usageMetadata, inputTokens, outputTokens, totalTokens, cacheTokens, isTruncated, cost, feedback } = reviewPayload;

    if (isTruncated) {
      return handleTruncation(true, finishReason, usageMetadata, summary, totalTokens, modelName);
    }



    return parseVisualReviewReturn(summary, feedback, totalTokens, inputTokens, outputTokens, cacheTokens, cost, modelName, isTruncated);
  }
};
