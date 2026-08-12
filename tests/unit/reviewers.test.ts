import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest';
import { GitHubModelFactory } from '../../src/reviewers/factory';
import { runReview, complete, normalizeModelId } from '../../src/reviewers/runner';
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
  it('correctly maps various case-insensitive names to official Azure/GitHub model IDs', () => {
    expect(normalizeModelId('gpt-4o')).toBe('gpt-4o');
    expect(normalizeModelId('gpt-4o-mini')).toBe('gpt-4o-mini');
    expect(normalizeModelId('deepseek-r1')).toBe('DeepSeek-R1');
    expect(normalizeModelId('llama-3.3-70b-instruct')).toBe('Llama-3.3-70B-Instruct');
    expect(normalizeModelId('phi-4')).toBe('Phi-4');
    expect(normalizeModelId('unrecognized-model')).toBe('unrecognized-model');
  });
});

describe('GitHubModelFactory', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
    GitHubModelFactory.resetClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  describe('getFallbackChain', () => {
    it('returns custom chain if AI_CHAIN_PRIMARY is set', () => {
      process.env.AI_CHAIN_PRIMARY = 'my-model';
      process.env.AI_CHAIN_FALLBACKS = 'fallback-1, fallback-2';
      const chain = GitHubModelFactory.getFallbackChain();
      expect(chain).toEqual(['my-model', 'fallback-1', 'fallback-2']);
    });

    it('returns fallbacks for grok-3', () => {
      process.env.AI_PROVIDER = 'grok-3';
      const chain = GitHubModelFactory.getFallbackChain();
      expect(chain).toEqual(['Grok 3', 'gpt-4o', 'gpt-4o-mini']);
    });

    it('returns fallbacks for deepseek', () => {
      process.env.AI_PROVIDER = 'deepseek';
      const chain = GitHubModelFactory.getFallbackChain();
      expect(chain).toEqual(['DeepSeek-R1', 'gpt-4o-mini', 'Phi-4']);
    });

    it('returns fallbacks for gpt-4', () => {
      process.env.AI_PROVIDER = 'gpt-4';
      const chain = GitHubModelFactory.getFallbackChain();
      expect(chain).toEqual(['gpt-4o', 'gpt-4o-mini', 'Phi-4']);
    });

    it('returns fallbacks for claude', () => {
      process.env.AI_PROVIDER = 'claude';
      const chain = GitHubModelFactory.getFallbackChain();
      expect(chain).toEqual(['claude-3-5-sonnet', 'gpt-4o-mini', 'Phi-4']);
    });

    it('defaults to gpt-4o-mini if AI_PROVIDER is unset or unknown', () => {
      delete process.env.AI_PROVIDER;
      const chain1 = GitHubModelFactory.getFallbackChain();
      expect(chain1).toEqual(['gpt-4o-mini', 'Phi-4-mini-instruct']);

      process.env.AI_PROVIDER = 'unknown-provider';
      const chain2 = GitHubModelFactory.getFallbackChain();
      expect(chain2).toEqual(['gpt-4o-mini', 'Phi-4-mini-instruct']);
    });
  });

  describe('getClient', () => {
    it('throws error if GITHUB_TOKEN is missing', () => {
      delete process.env.GITHUB_TOKEN;
      expect(() => GitHubModelFactory.getClient()).toThrow('Missing GITHUB_TOKEN environment variable.');
    });

    it('throws error if GITHUB_TOKEN format is invalid', () => {
      process.env.GITHUB_TOKEN = 'invalid token with spaces';
      expect(() => GitHubModelFactory.getClient()).toThrow('Invalid GITHUB_TOKEN format.');
    });

    it('returns cached OpenAI instance if GITHUB_TOKEN is present', () => {
      process.env.GITHUB_TOKEN = 'test-token';
      const client1 = GitHubModelFactory.getClient();
      expect(OpenAI).toHaveBeenCalledWith({
        baseURL: 'https://api.openai.com/v1',
        apiKey: 'test-token'
      });
      expect(client1).toBeDefined();

      const client2 = GitHubModelFactory.getClient();
      expect(client1).toBe(client2); // Singleton pattern
    });
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

  it('succeeds on first model if it does not throw', async () => {
    const mockClient = GitHubModelFactory.getClient();
    const createMock = mockClient.chat.completions.create as unknown as Mock;
    createMock.mockResolvedValueOnce({
      choices: [{ message: { content: 'Good review' } }]
    });

    process.env.AI_PROVIDER = 'phi-4';

    const result = await runReview({
      prContent: 'some changes',
      rules: ['no bugs']
    });

    expect(result).toBe('Good review');
    expect(createMock).toHaveBeenCalledTimes(1);
    expect(createMock).toHaveBeenLastCalledWith({
      model: 'Phi-4',
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
      primary: 'Phi-4',
      fallbacks: ['gpt-4o-mini'],
      max_retries: 2
    };

    const result = await complete(chain, {
      messages: [{ role: 'user', content: 'hello' }]
    });

    expect(result.content).toBe('Fallback review');
    expect(result.modelUsed).toBe('gpt-4o-mini');
    expect(createMock).toHaveBeenCalledTimes(3); // 2 failures on Phi-4, then 1 success on gpt-4o-mini
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('Usage/Rate limit or server error hit for Phi-4'));
    warnSpy.mockRestore();
  });

  it('rotates to next model immediately on non-recoverable error without retrying', async () => {
    const mockClient = GitHubModelFactory.getClient();
    const createMock = mockClient.chat.completions.create as unknown as Mock;

    // First model fails with unexpected error, rotates immediately
    createMock.mockRejectedValueOnce(new Error('Unexpected network glitch'));
    createMock.mockResolvedValueOnce({
      choices: [{ message: { content: 'Fallback review 2' } }]
    });

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const chain = {
      primary: 'Phi-4',
      fallbacks: ['gpt-4o-mini'],
      max_retries: 3
    };

    const result = await complete(chain, {
      messages: [{ role: 'user', content: 'hello' }]
    });

    expect(result.content).toBe('Fallback review 2');
    expect(result.modelUsed).toBe('gpt-4o-mini');
    expect(createMock).toHaveBeenCalledTimes(2); // 1 immediate failure, then fallback success
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('encountered an unexpected error: Unexpected network glitch'));
    warnSpy.mockRestore();
  });

  it('throws error immediately without fallback on hard failure (401 unauthorized)', async () => {
    const mockClient = GitHubModelFactory.getClient();
    const createMock = mockClient.chat.completions.create as unknown as Mock;

    createMock.mockRejectedValue({ status: 401, message: 'Unauthorized / Invalid Key' });

    const chain = {
      primary: 'Phi-4',
      fallbacks: ['gpt-4o-mini'],
      max_retries: 3
    };

    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    await expect(complete(chain, {
      messages: [{ role: 'user', content: 'hello' }]
    })).rejects.toEqual({ status: 401, message: 'Unauthorized / Invalid Key' });

    expect(createMock).toHaveBeenCalledTimes(1); // halts immediately on 401
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining('Hard failure (non-recoverable) encountered for model Phi-4'));
    errorSpy.mockRestore();
  });

  it('throws error if all models fail', async () => {
    const mockClient = GitHubModelFactory.getClient();
    const createMock = mockClient.chat.completions.create as unknown as Mock;

    createMock.mockRejectedValue(new Error('Persistent error'));

    process.env.AI_PROVIDER = 'phi-4';

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    await expect(runReview({
      prContent: 'some changes',
      rules: ['no bugs']
    })).rejects.toThrow('All requested GitHub Model providers and fallbacks failed or exhausted their usage limits.');

    // Phi-4 fallback chain is ["Phi-4", "gpt-4o-mini", "Phi-4-mini-instruct"], so it should try 3 times (once per model since they fail with unexpected error immediately)
    expect(createMock).toHaveBeenCalledTimes(3);
    warnSpy.mockRestore();
  });
});
