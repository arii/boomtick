import { describe, expect, it, vi } from 'vitest';

vi.mock('../../lib/geminiModelPicker', () => ({
  pickGeminiModel: vi.fn(async () => 'gemini-test-model'),
  getGeminiPricing: vi.fn(() => undefined),
}));

const FEEDBACK = [
  'Problem found.',
  '[VERDICT: FAIL]',
  '<findings>',
  JSON.stringify({
    findings: [
      { id: 'F1', file: 'src/app.ts', line: 3, issue: 'SQL injection.', status: 'open', severity: 'HIGH', confidence: 'high' },
    ],
  }),
  '</findings>',
].join('\n');

vi.mock('../../lib/geminiUtils', async importOriginal => {
  const actual = await importOriginal<typeof import('../../lib/geminiUtils')>();
  return {
    ...actual,
    invokeGeminiWithBudgetRetry: vi.fn(async () => ({
      response: { content: FEEDBACK, usage_metadata: { input_tokens: 10, output_tokens: 5, total_tokens: 15 } },
      finishReason: 'STOP',
    })),
  };
});

import { geminiCodeReviewClient } from '../../scripts/clients/geminiCodeReviewClient';

describe('geminiCodeReviewClient.invokeReview', () => {
  it('returns findings in state.findings, which the orchestrator aggregates and reconciles from', async () => {
    const result = await geminiCodeReviewClient.invokeReview({
      role: 'SECURITY',
      diffContext: 'diff --git a/src/app.ts b/src/app.ts',
      changedFiles: ['src/app.ts'],
    } as any);

    expect(result.llmVerdict).toBe('fail');
    expect(result.findings).toHaveLength(1);
    expect(result.state?.findings).toHaveLength(1);
    expect(result.state?.findings[0]).toMatchObject({ id: 'F1', status: 'open', severity: 'HIGH' });
  });
});
