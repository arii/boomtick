import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest';
import { GitHubModelFactory } from '../../src/reviewers/factory';
import { runReview } from '../../src/reviewers/runner';
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

describe('GitHubModelFactory', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
    vi.clearAllMocks();
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  describe('getFallbackChain', () => {
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

    it('returns OpenAI instance if GITHUB_TOKEN is present', () => {
      process.env.GITHUB_TOKEN = 'test-token';
      const client = GitHubModelFactory.getClient();
      expect(OpenAI).toHaveBeenCalledWith({
        baseURL: 'https://models.inference.ai.azure.com',
        apiKey: 'test-token'
      });
      expect(client).toBeDefined();
    });
  });
});

describe('runReview', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
    process.env.GITHUB_TOKEN = 'test-token';
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
        { role: 'user', content: 'Review the following Pull Request changes:\n\nsome changes' }
      ],
      temperature: 0.2
    });
  });

  it('rotates to next model on 429 rate limit error', async () => {
    const mockClient = GitHubModelFactory.getClient();
    const createMock = mockClient.chat.completions.create as unknown as Mock;

    // First model fails with 429 status
    createMock.mockRejectedValueOnce({
      status: 429,
      message: 'Rate limit exceeded'
    });
    // Second model succeeds
    createMock.mockResolvedValueOnce({
      choices: [{ message: { content: 'Fallback review' } }]
    });

    process.env.AI_PROVIDER = 'phi-4';

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const result = await runReview({
      prContent: 'some changes',
      rules: ['no bugs']
    });

    expect(result).toBe('Fallback review');
    expect(createMock).toHaveBeenCalledTimes(2);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('Usage/Rate limit hit for Phi-4'));
    warnSpy.mockRestore();
  });

  it('rotates to next model on other errors', async () => {
    const mockClient = GitHubModelFactory.getClient();
    const createMock = mockClient.chat.completions.create as unknown as Mock;

    // First model fails with standard error
    createMock.mockRejectedValueOnce(new Error('Network error'));
    // Second model succeeds
    createMock.mockResolvedValueOnce({
      choices: [{ message: { content: 'Fallback review 2' } }]
    });

    process.env.AI_PROVIDER = 'phi-4';

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const result = await runReview({
      prContent: 'some changes',
      rules: ['no bugs']
    });

    expect(result).toBe('Fallback review 2');
    expect(createMock).toHaveBeenCalledTimes(2);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('Model Phi-4 encountered an error: Network error'));
    warnSpy.mockRestore();
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

    // Phi-4 fallback chain is ["Phi-4", "gpt-4o-mini", "Phi-4-mini-instruct"], so it should try 3 times
    expect(createMock).toHaveBeenCalledTimes(3);
    warnSpy.mockRestore();
  });
});
