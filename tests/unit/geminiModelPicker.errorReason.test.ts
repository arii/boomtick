import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function pickerWith(response: unknown) {
  vi.resetModules();
  vi.stubEnv('GEMINI_MODEL', '');
  vi.stubEnv('GEMINI_API_KEY', 'mock-key-not-real');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
  return import('../../lib/geminiModelPicker');
}

describe('Gemini model list failures name the reason', () => {
  it('logs the status and reason codes from a 400 body, never the message or the key', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { pickGeminiModel } = await pickerWith({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      json: async () => ({
        error: {
          code: 400,
          message: 'API key not valid. Please pass a valid API key.',
          status: 'INVALID_ARGUMENT',
          details: [{ reason: 'API_KEY_INVALID' }],
        },
      }),
    });
    await expect(pickGeminiModel('lite')).rejects.toThrow();
    const lines = warn.mock.calls.map(args => args.join(' '));
    expect(lines.some(l => l.endsWith('Failed to fetch Gemini models: 400 Bad Request (INVALID_ARGUMENT, API_KEY_INVALID)'))).toBe(true);
    expect(lines.join('\n')).not.toContain('mock-key-not-real');
    expect(lines.join('\n')).not.toContain('Please pass');
  });

  it('keeps the old line when the body is not JSON', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { pickGeminiModel } = await pickerWith({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      json: async () => { throw new SyntaxError('not json'); },
    });
    await expect(pickGeminiModel('lite')).rejects.toThrow();
    const lines = warn.mock.calls.map(args => args.join(' '));
    expect(lines.some(l => l.endsWith('Failed to fetch Gemini models: 400 Bad Request'))).toBe(true);
  });
});
