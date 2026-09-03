import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { GitHubModelFactory } from '../../../src/reviewers/factory';
import { OpenAI } from 'openai';

// Mock OpenAI
vi.mock('openai', () => {
  return {
    OpenAI: vi.fn().mockImplementation(function (this: any, opts: any) {
      this.opts = opts;
    })
  };
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

  describe('getClient', () => {
    it('throws error if all token environment variables are missing', () => {
      delete process.env.OPENAI_API_KEY;
      delete process.env.OPEN_API_KEY;
      delete process.env.GITHUB_TOKEN;

      expect(() => GitHubModelFactory.getClient()).toThrow('Missing GITHUB_TOKEN environment variable.');
    });

    it('throws error if token format is invalid (fails regex validation)', () => {
      delete process.env.OPENAI_API_KEY;
      delete process.env.OPEN_API_KEY;
      process.env.GITHUB_TOKEN = 'invalid token with spaces';

      expect(() => GitHubModelFactory.getClient()).toThrow('Invalid GITHUB_TOKEN format.');
    });

    it('resolves OPENAI_API_KEY with OpenAI baseURL', () => {
      delete process.env.GITHUB_TOKEN;
      delete process.env.OPEN_API_KEY;
      process.env.OPENAI_API_KEY = 'sk-test-openai-key';

      const client = GitHubModelFactory.getClient();

      expect(OpenAI).toHaveBeenCalledWith({
        baseURL: 'https://api.openai.com/v1',
        apiKey: 'sk-test-openai-key'
      });
      expect(client).toBeDefined();
    });

    it('resolves OPEN_API_KEY fallback with OpenAI baseURL when OPENAI_API_KEY is unset', () => {
      delete process.env.GITHUB_TOKEN;
      delete process.env.OPENAI_API_KEY;
      process.env.OPEN_API_KEY = 'sk-test-open-api-key';

      const client = GitHubModelFactory.getClient();

      expect(OpenAI).toHaveBeenCalledWith({
        baseURL: 'https://api.openai.com/v1',
        apiKey: 'sk-test-open-api-key'
      });
      expect(client).toBeDefined();
    });

    it('resolves GITHUB_TOKEN with Azure inference baseURL when OpenAI keys are unset', () => {
      delete process.env.OPENAI_API_KEY;
      delete process.env.OPEN_API_KEY;
      process.env.GITHUB_TOKEN = 'ghp_test_github_token';

      const client = GitHubModelFactory.getClient();

      expect(OpenAI).toHaveBeenCalledWith({
        baseURL: 'https://models.inference.ai.azure.com',
        apiKey: 'ghp_test_github_token'
      });
      expect(client).toBeDefined();
    });

    it('prioritizes OPENAI_API_KEY over GITHUB_TOKEN', () => {
      process.env.OPENAI_API_KEY = 'sk-openai-priority';
      process.env.GITHUB_TOKEN = 'ghp_github_token';

      GitHubModelFactory.getClient();

      expect(OpenAI).toHaveBeenCalledWith({
        baseURL: 'https://api.openai.com/v1',
        apiKey: 'sk-openai-priority'
      });
    });

    it('reuses cached instance on repeated calls (Singleton pattern)', () => {
      process.env.GITHUB_TOKEN = 'ghp_test_token';

      const client1 = GitHubModelFactory.getClient();
      const client2 = GitHubModelFactory.getClient();

      expect(OpenAI).toHaveBeenCalledTimes(1);
      expect(client1).toBe(client2);
    });

    it('creates a new instance after resetClient() is called', () => {
      process.env.GITHUB_TOKEN = 'ghp_test_token';

      const client1 = GitHubModelFactory.getClient();
      GitHubModelFactory.resetClient();
      const client2 = GitHubModelFactory.getClient();

      expect(OpenAI).toHaveBeenCalledTimes(2);
      expect(client1).not.toBe(client2);
    });
  });

  describe('getFallbackChain', () => {
    it('returns custom chain if AI_CHAIN_PRIMARY and AI_CHAIN_FALLBACKS are set', () => {
      process.env.AI_CHAIN_PRIMARY = 'custom-model';
      process.env.AI_CHAIN_FALLBACKS = 'fallback-1, fallback-2';

      const chain = GitHubModelFactory.getFallbackChain();
      expect(chain).toEqual(['custom-model', 'fallback-1', 'fallback-2']);
    });

    it('returns custom primary without fallbacks if AI_CHAIN_FALLBACKS is unset', () => {
      process.env.AI_CHAIN_PRIMARY = 'custom-model-only';
      delete process.env.AI_CHAIN_FALLBACKS;

      const chain = GitHubModelFactory.getFallbackChain();
      expect(chain).toEqual(['custom-model-only']);
    });

    it('returns preset fallback chain for gpt-4o-mini provider', () => {
      delete process.env.AI_CHAIN_PRIMARY;
      process.env.AI_PROVIDER = 'gpt-4o-mini';

      const chain = GitHubModelFactory.getFallbackChain();
      expect(chain).toEqual(['gpt-4o-mini', 'gpt-4o']);
    });

    it('returns preset fallback chain for gpt-4 provider', () => {
      delete process.env.AI_CHAIN_PRIMARY;
      process.env.AI_PROVIDER = 'gpt-4';

      const chain = GitHubModelFactory.getFallbackChain();
      expect(chain).toEqual(['gpt-4o', 'gpt-4o-mini']);
    });

    it('defaults to ["gpt-4o-mini"] if AI_PROVIDER is unset or unknown', () => {
      delete process.env.AI_CHAIN_PRIMARY;
      delete process.env.AI_PROVIDER;

      const chain1 = GitHubModelFactory.getFallbackChain();
      expect(chain1).toEqual(['gpt-4o-mini']);

      process.env.AI_PROVIDER = 'unknown-provider';
      const chain2 = GitHubModelFactory.getFallbackChain();
      expect(chain2).toEqual(['gpt-4o-mini']);
    });
  });
});
