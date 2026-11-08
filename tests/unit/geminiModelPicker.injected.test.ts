import { describe, expect, it } from 'vitest';

// Catalog visible to the picker in these tests only: one model that exists
// nowhere in the shipped data file, plus a distinctive default. If the picker
// consulted anything but the data file, neither value could surface here.
vi.mock('../../data/gemini-models.json', () => ({
  default: {
    version: 1,
    updated: '2026-11-08',
    defaultPricing: { inputCostPerM: 0.11, outputCostPerM: 0.44 },
    models: [
      {
        id: 'gemini-9.9-test-injected',
        name: 'Injected Test Model',
        tier: 'flash',
        maxInputTokens: 1000,
        maxOutputTokens: 100,
        inputCostPerM: 7.77,
        outputCostPerM: 8.88,
        reviewAfter: null,
        deprecatedAfter: null,
      },
    ],
    deprecated: [],
  },
}));

describe('geminiModelPicker injected catalog entry (issue #1227)', () => {
  it('prices a model added only to the data file', async () => {
    const picker = await import('../../lib/geminiModelPicker');
    expect(picker.getGeminiPricing('gemini-9.9-test-injected')).toEqual({
      inputCostPerM: 7.77,
      outputCostPerM: 8.88,
    });
  });

  it('uses the data file default for ids it does not list', async () => {
    const picker = await import('../../lib/geminiModelPicker');
    expect(picker.getGeminiPricing('gemini-unknown-xyz')).toEqual({
      inputCostPerM: 0.11,
      outputCostPerM: 0.44,
    });
  });
});
