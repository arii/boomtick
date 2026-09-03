import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest';
import { GitHubModelFactory } from '../../../src/reviewers/factory';
import { runReview, complete, normalizeModelId } from '../../../src/reviewers/runner';
import { OpenAI } from 'openai';

const mockCreate = vi.fn();

// Mock OpenAI
vi.mock('openai', () => {
  return {
    OpenAI: vi.fn().mockImplementation(function (this: any) {
      this.chat = {
        completions: {
          create: mockCreate
        }
      };
    })
  };
});

describe('normalizeModelId', () => {
  it('correctly maps gpt-4o and gpt-4o-mini regardless of casing', () => {
    expect(normalizeModelId('gpt-4o')).toBe('gpt-4o');
    expect(normalizeModelId('GPT-4O')).toBe('gpt-4o');
    expect(normalizeModelId('Gpt-4o')).toBe('gpt-4o');

    expect(normalizeModelId('gpt-4o-mini')).toBe('gpt-4o-mini');
    expect(normalizeModelId('GPT-4O-MINI')).toBe('gpt-4o-mini');
    expect(normalizeModelId('Gpt-4o-Mini')).toBe('gpt-4o-mini');
  });

  it('returns original model string for unrecognized or other model IDs', () => {
    expect(normalizeModelId('unrecognized-model')).toBe('unrecognized-model');
    expect(normalizeModelId('claude-3-5-sonnet')).toBe('claude-3-5-sonnet');
    expect(normalizeModelId('gpt-4')).toBe('gpt-4');
  });
});

describe('runReview & complete', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
    process.env.GITHUB_TOKEN = 'test-token';
    GitHubModelFactory.resetClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it('succeeds on first model if request succeeds', async () => {
    const mockClient = GitHubModelFactory.getClient();
    const createMock = mockClient.chat.completions.create as unknown as Mock;
    createMock.mockResolvedValueOnce({
      choices: [{ message: { content: 'Good review' } }]
    });

    process.env.AI_PROVIDER = 'gpt-4o-mini';

    const result = await runReview({
      prContent: 'some changes',
      rules: ['no bugs']
    });

    expect(result).toBe('Good review');
    expect(createMock).toHaveBeenCalledTimes(1);
    expect(createMock).toHaveBeenLastCalledWith({
      model: 'gpt-4o-mini',
      messages: [
        { role: 'system', content: 'You are an expert automated code review agent. Rules to enforce:\nno bugs' },
        { role: 'user', content: 'Review the following Pull Request changes:\n\n<pr_content>\nsome changes\n</pr_content>' }
      ],
      temperature: 0.2,
      max_tokens: undefined
    });
  });

  it('rotates to next model on 429 rate limit error after exhausting retries', async () => {
    const mockClient = GitHubModelFactory.getClient();
    const createMock = mockClient.chat.completions.create as unknown as Mock;

    // First model fails twice with 429, then rotates to backup model which succeeds
    createMock.mockRejectedValueOnce({ status: 429, message: 'Rate limit' });
    createMock.mockRejectedValueOnce({ status: 429, message: 'Rate limit' });
    createMock.mockResolvedValueOnce({
      choices: [{ message: { content: 'Fallback review' } }]
    });

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const chain = {
      primary: 'gpt-4o',
      fallbacks: ['gpt-4o-mini'],
      max_retries: 2
    };

    const result = await complete(chain, {
      messages: [{ role: 'user', content: 'hello' }]
    });

    expect(result.content).toBe('Fallback review');
    expect(result.modelUsed).toBe('gpt-4o-mini');
    expect(createMock).toHaveBeenCalledTimes(3);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('Usage/Rate limit or server error hit for gpt-4o'));
    warnSpy.mockRestore();
  });

  it('rotates to next model immediately on unexpected non-recoverable error without retrying', async () => {
    const mockClient = GitHubModelFactory.getClient();
    const createMock = mockClient.chat.completions.create as unknown as Mock;

    createMock.mockRejectedValueOnce(new Error('Unexpected network glitch'));
    createMock.mockResolvedValueOnce({
      choices: [{ message: { content: 'Fallback review 2' } }]
    });

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const chain = {
      primary: 'gpt-4o',
      fallbacks: ['gpt-4o-mini'],
      max_retries: 3
    };

    const result = await complete(chain, {
      messages: [{ role: 'user', content: 'hello' }]
    });

    expect(result.content).toBe('Fallback review 2');
    expect(result.modelUsed).toBe('gpt-4o-mini');
    expect(createMock).toHaveBeenCalledTimes(2);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('encountered an unexpected error: Unexpected network glitch'));
    warnSpy.mockRestore();
  });

  it('throws error immediately without fallback on hard failure (401 unauthorized)', async () => {
    const mockClient = GitHubModelFactory.getClient();
    const createMock = mockClient.chat.completions.create as unknown as Mock;

    createMock.mockRejectedValue({ status: 401, message: 'Unauthorized / Invalid Key' });

    const chain = {
      primary: 'gpt-4o',
      fallbacks: ['gpt-4o-mini'],
      max_retries: 3
    };

    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    await expect(complete(chain, {
      messages: [{ role: 'user', content: 'hello' }]
    })).rejects.toEqual({ status: 401, message: 'Unauthorized / Invalid Key' });

    expect(createMock).toHaveBeenCalledTimes(1);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining('Hard failure (non-recoverable) encountered for model gpt-4o'));
    errorSpy.mockRestore();
  });

  it('throws error if all models in fallback chain fail', async () => {
    const mockClient = GitHubModelFactory.getClient();
    const createMock = mockClient.chat.completions.create as unknown as Mock;

    createMock.mockRejectedValue(new Error('Persistent error'));

    process.env.AI_PROVIDER = 'gpt-4';

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    await expect(runReview({
      prContent: 'some changes',
      rules: ['no bugs']
    })).rejects.toThrow('All requested GitHub Model providers and fallbacks failed or exhausted their usage limits.');

    expect(createMock).toHaveBeenCalledTimes(2);
    warnSpy.mockRestore();
  });
});
