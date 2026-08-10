import {
  parseCodeReviewVerdict,
  parseCodeReviewStateDetailed,
  budgetInputContext,
  extractFeedbackText,
} from '../../lib/codeReviewUtils';
import { buildSystemPrompt } from '../../lib/buildCodeReviewPrompt';
import type { CodeReviewSummary, CodeReviewResult } from '../../lib/codeReviewTypes';
import type { CodeReviewClientStrategy } from '../../lib/codeReviewOrchestrator';
import { complete } from '../../src/reviewers/runner';
import { GitHubModelFactory } from '../../src/reviewers/factory';
import { loadProjectConfig } from '../../lib/projectConfig';

function parseTriageResult(content: string): { needsSpecialistReview: boolean; reason?: string; fastFeedback?: string } {
  try {
    const match = content.match(/<triage_result>([\s\S]*?)<\/triage_result>/);
    const jsonStr = match ? match[1].trim() : content.trim();
    const parsed = JSON.parse(jsonStr);
    return {
      needsSpecialistReview: !!parsed.needsSpecialistReview,
      reason: parsed.reason,
      fastFeedback: parsed.fastFeedback
    };
  } catch (err) {
    console.warn("⚠️ Failed to parse triage JSON result, falling back to Specialist review for safety:", err);
    return { needsSpecialistReview: true }; // default to safe specialist fallback
  }
}

export const githubModelsCodeReviewClient: CodeReviewClientStrategy = {
  botName: 'github-models-code-review',
  reportTitle: '🐙 GitHub Models Code Review',
  botTagline: 'Powered by GitHub Models with Dynamic Provider Strategy',
  reportFileName: 'github-models-code-review.md',

  invokeReview: async (summary: CodeReviewSummary, forceMaxOutputTokens?: number): Promise<CodeReviewResult> => {
    const systemPrompt = buildSystemPrompt(summary);
    const { diffText, externalText } = budgetInputContext(systemPrompt, summary);

    const fallbackChain = GitHubModelFactory.getFallbackChain();

    // 1. Run Triage Step
    const triageSystemPrompt = `You are an expert AI Triage Agent. Your task is to perform a fast, initial validation on the Pull Request diff.
Determine if there are complex architectural issues, critical bugs, security vulnerabilities, or performance issues that require a deeper, specialized review for the role: ${summary.role || 'General'}.

You must respond strictly in JSON format matching this schema:
{
  "needsSpecialistReview": boolean,
  "reason": "string describing why a specialist is or is not needed",
  "fastFeedback": "string of initial review feedback if no specialist is needed"
}

Your output must be wrapped inside a single block of XML tags like this:
<triage_result>
{
  "needsSpecialistReview": ...
}
</triage_result>
`;

    const triageMessages = [
      { role: "system" as const, content: triageSystemPrompt },
      { role: "user" as const, content: `Review the following changes and requirements:\n\n<diff>\n${diffText}\n</diff>\n\nREQUIREMENTS/GOALS:\n${summary.prGoal || 'Analyze code quality.'}` }
    ];

    const projConfig = loadProjectConfig();

    const triageChain = {
      primary: process.env.AI_TRIAGE_CHAIN_PRIMARY || projConfig.triage_chain?.primary || 'gpt-4o-mini',
      fallbacks: process.env.AI_TRIAGE_CHAIN_FALLBACKS
        ? process.env.AI_TRIAGE_CHAIN_FALLBACKS.split(',').map(s => s.trim())
        : (projConfig.triage_chain?.fallbacks || ['gpt-4o']),
      max_retries: projConfig.triage_chain?.max_retries ?? 2
    };

    console.log(`[AI Triage] Invoking Triage Agent using fast/cheap model...`);
    let needsSpecialist = true;
    let fastFeedbackText = "";
    let triageModelUsed = "gpt-4o-mini";

    try {
      const triageRes = await complete(triageChain, { messages: triageMessages, temperature: 0.1 });
      triageModelUsed = triageRes.modelUsed;
      const parsedTriage = parseTriageResult(triageRes.content);
      needsSpecialist = parsedTriage.needsSpecialistReview;
      fastFeedbackText = parsedTriage.fastFeedback || "";
      console.log(`[AI Triage Success] Triage complete. Needs specialist: ${needsSpecialist}. Model: ${triageModelUsed}`);
    } catch (err) {
      console.warn("⚠️ Triage Agent failed, falling back to Specialist review:", err);
    }

    let finalFeedback = "";
    let finalModelUsed = "";

    if (!needsSpecialist && fastFeedbackText) {
      console.log(`[AI Triage] Fast triage review sufficient. Bypassing specialist review.`);
      finalFeedback = fastFeedbackText;
      finalModelUsed = `${triageModelUsed} (Triage)`;
    } else {
      // 2. Specialist Step (Omits triage agent's reasoning to preserve isolation)
      const specialistChain = {
        primary: process.env.AI_SPECIALIST_CHAIN_PRIMARY || fallbackChain[0] || 'gpt-4o',
        fallbacks: process.env.AI_SPECIALIST_CHAIN_FALLBACKS
          ? process.env.AI_SPECIALIST_CHAIN_FALLBACKS.split(',').map(s => s.trim())
          : (fallbackChain.slice(1).length > 0 ? fallbackChain.slice(1) : ['gpt-4o-mini']),
        max_retries: 3
      };

      const prContent = `DIFF:\n\n${diffText}` + (externalText ? `\n\nEXTERNAL CONTEXT:\n\n${externalText}` : '');

      console.log(`[AI Specialist] Handing off to Specialist Agent for deep review due to high complexity...`);
      const specialistMessages = [
        { role: "system" as const, content: systemPrompt },
        { role: "user" as const, content: prContent }
      ];

      const specialistRes = await complete(specialistChain, {
        messages: specialistMessages,
        temperature: 0.2,
        maxTokens: forceMaxOutputTokens
      });

      finalFeedback = specialistRes.content;
      finalModelUsed = `${specialistRes.modelUsed} (Specialist)`;
    }

    const cleanFeedback = extractFeedbackText(finalFeedback);
    const parsedState = parseCodeReviewStateDetailed(cleanFeedback);

    return {
      feedback: cleanFeedback,
      role: summary.role,
      tokens: 0,
      inputTokens: 0,
      outputTokens: 0,
      cacheTokens: 0,
      cost: 0,
      llmVerdict: parseCodeReviewVerdict(cleanFeedback),
      state: parsedState.state,
      modelName: finalModelUsed,
      isTruncated: false,
      parseError: parsedState.parseError,
    };
  }
};
