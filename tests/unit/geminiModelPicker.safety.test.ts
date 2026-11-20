import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../lib/gemini-models.json', () => ({ default: {
  models: [
    { id: 'active-test', tier: 'lite', maxInputTokens: 1000, deprecatedAfter: null },
    { id: 'retired-test', tier: 'flash', maxInputTokens: 2000, deprecatedAfter: '2026-12-01' },
  ], deprecated: [], defaultPricing: { inputCostPerM: 1, outputCostPerM: 2 },
} }));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  vi.resetModules();
});

async function picker(ids: string[], date = '2026-12-01T00:00:00Z') {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(date));
  vi.stubEnv('GEMINI_MODEL', '');
  vi.stubEnv('GEMINI_API_KEY', 'mock-key-not-real');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: true, json: async () => ({models: ids.map(id => ({name: `models/${id}`}))})}));
  return import('../../lib/geminiModelPicker');
}

describe('Gemini selection is verified and capacity-aware', () => {
  it('rejects unknown live IDs instead of bypassing the catalog', async () => {
    const p = await picker(['gemini-3.5-unknown']);
    await expect(p.pickGeminiModel()).rejects.toThrow('No verified active');
  });
  it('excludes models starting exactly on their deprecation boundary', async () => {
    const p = await picker(['retired-test', 'active-test']);
    expect(await p.pickGeminiModel('flash')).toBe('active-test');
  });
  it('allows a catalog model before its boundary', async () => {
    const p = await picker(['retired-test'], '2026-11-30T23:59:59Z');
    expect(await p.pickGeminiModel('flash')).toBe('retired-test');
  });
  it('does not return an undersized model', async () => {
    const p = await picker(['active-test']);
    await expect(p.pickGeminiModel('lite', 1001)).rejects.toThrow('No verified active');
  });
  it('does not fall back to unavailable catalog IDs after discovery failure', async () => {
    const p = await picker([]);
    await expect(p.pickGeminiModel()).rejects.toThrow('No verified active');
  });
  it('preserves explicit operator model override', async () => {
    const p = await picker([]);
    vi.stubEnv('GEMINI_MODEL', 'operator-choice');
    expect(await p.pickGeminiModel()).toBe('operator-choice');
  });
});
