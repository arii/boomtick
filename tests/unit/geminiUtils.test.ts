import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createGeminiModel, getConfiguredTokens, applyRetryStrategy, extractFinishReason } from '../../lib/geminiUtils';

describe('geminiUtils', () => {
  beforeEach(() => {
    vi.stubEnv('GEMINI_API_KEY', 'fake-api-key');
  });

  it('getConfiguredTokens returns expected default values', () => {
    const codeTokens = getConfiguredTokens('code');
    expect(codeTokens.maxOutputTokens).toBe(6000);
    expect(codeTokens.thinkingBudget).toBe(2048);

    const visualTokens = getConfiguredTokens('visual');
    expect(visualTokens.maxOutputTokens).toBe(4096);
    expect(visualTokens.thinkingBudget).toBe(1024);
  });

  it('applyRetryStrategy adjusts tokens and budget correctly', () => {
    const { newMax, newThinking } = applyRetryStrategy(1000, 500);
    expect(newMax).toBe(1250);
    expect(newThinking).toBe(250);
  });

  it('extractFinishReason identifies finish reasons', () => {
    const res1 = { response_metadata: { finishReason: 'STOP' } };
    expect(extractFinishReason(res1)).toBe('STOP');

    const res2 = { response_metadata: { finish_reason: 'MAX_TOKENS' } };
    expect(extractFinishReason(res2)).toBe('MAX_TOKENS');

    const res3 = { generationInfo: { finishReason: 'SAFETY' } };
    expect(extractFinishReason(res3)).toBe('SAFETY');

    const res4 = { response_metadata: { candidates: [{ finishReason: 'RECITATION' }] } };
    expect(extractFinishReason(res4)).toBe('RECITATION');

    expect(extractFinishReason({})).toBe('UNKNOWN');
  });

  it('createGeminiModel instantiates DirectGeminiModel with correct properties', async () => {
    const model = await createGeminiModel('gemini-2.5-flash', 100, 50);
    expect(model).toBeDefined();
    expect(model.model).toBe('gemini-2.5-flash');
    expect(model.maxOutputTokens).toBe(100);
  });

  it('createGeminiModel throws when API key is missing', async () => {
    vi.stubEnv('GEMINI_API_KEY', '');
    await expect(createGeminiModel('gemini-2.5-flash', 100, 50)).rejects.toThrow('Missing GEMINI_API_KEY environment variable');
  });

  it('DirectGeminiModel.invoke performs a POST fetch request with the correct payload', async () => {
    const mockResponseData = {
      candidates: [
        {
          content: {
            parts: [{ text: 'Mocked Gemini feedback response' }]
          },
          finishReason: 'STOP'
        }
      ],
      usageMetadata: {
        promptTokenCount: 10,
        candidatesTokenCount: 20,
        totalTokenCount: 30
      }
    };

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => mockResponseData,
    } as any);

    const model = await createGeminiModel('gemini-2.5-flash', 100, 50);
    const result = await model.invoke([{ content: 'Hello Gemini!' }]);

    expect(fetchSpy).toHaveBeenCalled();
    const [calledUrl, calledInit] = fetchSpy.mock.calls[0];
    expect(calledUrl).toContain('https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=fake-api-key');
    expect(calledInit?.method).toBe('POST');

    const requestBody = JSON.parse(calledInit?.body as string);
    expect(requestBody.contents[0].parts[0].text).toBe('Hello Gemini!');
    expect(requestBody.generationConfig.maxOutputTokens).toBe(100);
    expect(requestBody.generationConfig.thinkingConfig.thinkingBudget).toBe(50);

    expect(result.content).toBe('Mocked Gemini feedback response');
    expect(result.usage_metadata.total_tokens).toBe(30);

    fetchSpy.mockRestore();
  });
});
