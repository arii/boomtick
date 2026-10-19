import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { initializeGitHubAuth } from '../../lib/githubAuth';

vi.mock('@octokit/auth-app', () => ({
  createAppAuth: vi.fn(() => vi.fn(async ({ type }) => {
    if (type === 'app') {
      return { token: 'mock-jwt-token' };
    }
    if (type === 'installation') {
      return { token: 'mock-installation-token' };
    }
    return { token: 'unknown' };
  })),
}));

describe('initializeGitHubAuth', () => {
  const originalEnv = { ...process.env };

  beforeEach(() => {
    process.env = { ...originalEnv };
    delete process.env.GITHUB_APP_ID;
    delete process.env.APP_ID;
    delete process.env.GITHUB_APP_PRIVATE_KEY;
    delete process.env.APP_PRIVATE_KEY;
    delete process.env.GITHUB_TOKEN;
    delete process.env.GITHUB_REPOSITORY;
    vi.restoreAllMocks();
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it('mints installation token successfully when App credentials and repo are provided', async () => {
    process.env.GITHUB_APP_ID = '12345';
    process.env.GITHUB_APP_PRIVATE_KEY = '-----BEGIN PRIVATE KEY-----\\nmock\\n-----END PRIVATE KEY-----';
    process.env.GITHUB_REPOSITORY = 'owner/repo';

    const globalFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 9999 }),
    });
    vi.stubGlobal('fetch', globalFetch);

    await initializeGitHubAuth();

    expect(process.env.GITHUB_TOKEN).toBe('mock-installation-token');
    expect(globalFetch).toHaveBeenCalledWith(
      'https://api.github.com/repos/owner/repo/installation',
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer mock-jwt-token',
        }),
      })
    );
  });

  it('falls back when GITHUB_REPOSITORY is missing', async () => {
    process.env.GITHUB_APP_ID = '12345';
    process.env.GITHUB_APP_PRIVATE_KEY = 'key';

    await initializeGitHubAuth();

    expect(process.env.GITHUB_TOKEN).toBeUndefined();
  });

  it('keeps GITHUB_TOKEN fallback when App credentials are not provided', async () => {
    process.env.GITHUB_TOKEN = 'fallback-token';

    await initializeGitHubAuth();

    expect(process.env.GITHUB_TOKEN).toBe('fallback-token');
  });
});
