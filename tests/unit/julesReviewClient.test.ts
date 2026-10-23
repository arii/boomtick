import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as fs from 'fs';
import { sendJulesImpactReport, calculateJulesRemediationHash, checkJulesStatus } from '../../lib/julesReviewClient';
import * as visualReviewUtils from '../../lib/visualReviewUtils';

vi.mock('fs', () => {
  return {
    existsSync: vi.fn().mockReturnValue(false),
    promises: {
      stat: vi.fn().mockResolvedValue({ isDirectory: () => true } as any),
      readdir: vi.fn().mockResolvedValue([]),
      readFile: vi.fn().mockResolvedValue(''),
      writeFile: vi.fn().mockResolvedValue(undefined),
    },
  };
});

vi.mock('../../lib/visualReviewUtils', () => ({
  getJulesSessionIdFromPR: vi.fn(),
}));

describe('julesReviewClient - sendJulesImpactReport', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    vi.clearAllMocks();
    process.env = { ...originalEnv };
    delete process.env.TASK_ID;
    delete process.env.JULES_API_KEY;
    global.fetch = vi.fn();
  });

  afterEach(() => {
    process.env = originalEnv;
    vi.restoreAllMocks();
  });

  it('exits gracefully if no taskId is provided or found', async () => {
    vi.mocked(visualReviewUtils.getJulesSessionIdFromPR).mockResolvedValue(null);
    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    await sendJulesImpactReport();

    expect(consoleSpy).toHaveBeenCalledWith("No TASK_ID provided or found in PR description. Exiting.");
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('exits gracefully if JULES_API_KEY is missing', async () => {
    process.env.TASK_ID = '12345';
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    await sendJulesImpactReport();

    expect(consoleSpy).toHaveBeenCalledWith(
      '⚠️  Skipping sending message to Jules session — JULES_API_KEY not set.'
    );
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('exits gracefully if artifacts directory does not exist', async () => {
    process.env.TASK_ID = '12345';
    process.env.JULES_API_KEY = 'test-key';

    vi.mocked(fs.promises.stat).mockRejectedValueOnce(new Error('ENOENT'));
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    await sendJulesImpactReport();

    expect(consoleSpy).toHaveBeenCalledWith(
      "Artifacts directory 'artifacts' not found. Cannot send impact analysis."
    );
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('skips sending if no actionable issues are found in verdict JSONs', async () => {
    process.env.TASK_ID = '12345';
    process.env.JULES_API_KEY = 'test-key';

    vi.mocked(fs.promises.stat).mockResolvedValue({ isDirectory: () => true } as fs.Stats);
    vi.mocked(fs.existsSync).mockReturnValue(false);
    vi.mocked(fs.promises.readdir).mockResolvedValue(['gemini-code-review-verdict.json'] as any);
    vi.mocked(fs.promises.readFile).mockResolvedValue(
      JSON.stringify({ passed: true, highCount: 0, llmVerdict: 'pass' })
    );

    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    await sendJulesImpactReport();

    expect(consoleSpy).toHaveBeenCalledWith(
      "No actionable issues/failures found in reviews. Skipping sending message to Jules."
    );
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('skips sending report if duplicate dispatch hash exists for session', async () => {
    process.env.TASK_ID = '12345';
    process.env.JULES_API_KEY = 'test-key';
    process.env.GITHUB_SHA = 'sha12345';

    vi.mocked(fs.promises.stat).mockResolvedValue({ isDirectory: () => true } as fs.Stats);

    const bodyContent = '## Deployment Impact Analysis\n\n### Deployment Summary\nHigh impact\n\n## Verdict JSONs\n### gemini-code-review-verdict.json\n```json\n{"passed":false,"highCount":1,"llmVerdict":"fail"}\n```\n\n';
    const hash = calculateJulesRemediationHash('sha12345', bodyContent);

    vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
      const pStr = String(p);
      if (pStr.includes('.jules-dispatch-')) return true;
      if (pStr.endsWith('artifacts')) return true;
      if (pStr.includes('deployment-review.md')) return true;
      return false;
    });

    vi.mocked(fs.promises.readdir).mockImplementation(async (p: unknown) => {
      if (String(p).includes('artifacts')) return ['gemini-code-review-verdict.json'] as any;
      return [];
    });
    vi.mocked(fs.promises.readFile).mockImplementation(async (p: unknown) => {
      const pStr = String(p);
      if (pStr.includes('.jules-dispatch-')) return hash;
      if (pStr.includes('deployment-review.md')) return '### Deployment Summary\nHigh impact';
      if (pStr.includes('verdict.json')) {
        return JSON.stringify({ passed: false, highCount: 1, llmVerdict: 'fail' });
      }
      return '';
    });

    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    await sendJulesImpactReport('12345');

    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining('Duplicate Jules dispatch skipped for session')
    );
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('sends report to Jules API when actionable issues exist', async () => {
    process.env.TASK_ID = '12345';
    process.env.JULES_API_KEY = 'test-key';

    vi.mocked(fs.promises.stat).mockResolvedValue({ isDirectory: () => true } as fs.Stats);
    vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
      const pStr = String(p);
      if (pStr.includes('deployment-review.md')) return true;
      if (pStr.includes('gemini-code-review.md')) return true;
      return false;
    });

    vi.mocked(fs.promises.readdir).mockImplementation(async (p: unknown) => {
      if (String(p).includes('artifacts')) return ['gemini-code-review-verdict.json'] as any;
      return [];
    });
    vi.mocked(fs.promises.readFile).mockImplementation(async (p: unknown) => {
      const pStr = String(p);
      if (pStr.includes('deployment-review.md')) return '### Deployment Summary\nHigh impact';
      if (pStr.includes('gemini-code-review.md')) return '### Code Review Feedback\nIssue found';
      if (pStr.includes('verdict.json')) {
        return JSON.stringify({ passed: false, highCount: 1, llmVerdict: 'fail' });
      }
      return '';
    });

    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue('OK'),
    } as any);

    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    await sendJulesImpactReport('12345');

    expect(global.fetch).toHaveBeenCalledWith(
      'https://jules.googleapis.com/v1alpha/sessions/12345:sendMessage',
      expect.objectContaining({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-goog-api-key': 'test-key',
        },
        body: expect.stringContaining('High impact'),
      })
    );

    expect(consoleSpy).toHaveBeenCalledWith('✅ Sent impact analysis to sessions/12345');
  });

  it('resolves taskId from getJulesSessionIdFromPR if argument and process.env are empty', async () => {
    process.env.JULES_API_KEY = 'test-key';
    vi.mocked(visualReviewUtils.getJulesSessionIdFromPR).mockResolvedValue('sessions/pr-session-999');

    vi.mocked(fs.promises.stat).mockResolvedValue({ isDirectory: () => true } as fs.Stats);
    vi.mocked(fs.existsSync).mockReturnValue(false);
    vi.mocked(fs.promises.readdir).mockImplementation(async (p: unknown) => {
      if (String(p).includes('artifacts')) return ['gemini-code-review-verdict.json'] as any;
      return [];
    });
    vi.mocked(fs.promises.readFile).mockResolvedValue(
      JSON.stringify({ passed: false, highCount: 1, llmVerdict: 'fail' })
    );

    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue('OK'),
    } as any);

    await sendJulesImpactReport();

    expect(global.fetch).toHaveBeenCalledWith(
      'https://jules.googleapis.com/v1alpha/sessions/pr-session-999:sendMessage',
      expect.anything()
    );
  });
});

describe('julesReviewClient - checkJulesStatus', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    vi.clearAllMocks();
    process.env = { ...originalEnv };
    delete process.env.TASK_ID;
    delete process.env.JULES_API_KEY;
    global.fetch = vi.fn();
  });

  afterEach(() => {
    process.env = originalEnv;
    vi.restoreAllMocks();
  });

  it('returns NOT_FOUND if no session ID provided or found', async () => {
    vi.mocked(visualReviewUtils.getJulesSessionIdFromPR).mockResolvedValue(null);

    const res = await checkJulesStatus();

    expect(res.status).toBe('NOT_FOUND');
    expect(res.completed).toBe(false);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('returns NOT_FOUND if JULES_API_KEY is missing', async () => {
    const res = await checkJulesStatus({ sessionId: '12345' });

    expect(res.status).toBe('NOT_FOUND');
    expect(res.completed).toBe(false);
    expect(res.message).toBe('JULES_API_KEY environment variable not set.');
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('fetches session status and returns COMPLETED when state is SUCCEEDED', async () => {
    process.env.JULES_API_KEY = 'test-key';

    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        name: 'sessions/12345',
        state: 'SUCCEEDED',
        sourceContext: {
          githubRepoContext: {
            startingBranch: 'jules-fix-branch',
          },
        },
        outputs: [
          {
            pullRequest: {
              url: 'https://github.com/org/repo/pull/42',
              branch: 'jules-fix-branch',
            },
          },
        ],
      }),
    } as any);

    const res = await checkJulesStatus({ sessionId: '12345' });

    expect(res.status).toBe('COMPLETED');
    expect(res.completed).toBe(true);
    expect(res.remediationBranch).toBe('jules-fix-branch');
    expect(res.pullRequestUrl).toBe('https://github.com/org/repo/pull/42');
  });

  it('calculates idempotency key and detects duplicate when hash matches', async () => {
    process.env.JULES_API_KEY = 'test-key';
    const commitSha = 'sha12345';
    const failureLog = 'Build failed at step 3';
    const expectedHash = calculateJulesRemediationHash(commitSha, failureLog);

    vi.mocked(fs.existsSync).mockImplementation((p: unknown) => String(p).includes('.jules-dispatch-'));
    vi.mocked(fs.promises.readFile).mockImplementation(async (p: unknown) => {
      if (String(p).includes('.jules-dispatch-')) {
        return expectedHash;
      }
      return '';
    });

    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        name: 'sessions/12345',
        state: 'IN_PROGRESS',
      }),
    } as any);

    const res = await checkJulesStatus({
      sessionId: '12345',
      commitSha,
      failureLog,
    });

    expect(res.idempotencyHash).toBe(expectedHash);
    expect(res.isDuplicate).toBe(true);
    expect(res.status).toBe('IN_PROGRESS');
  });

  it('polls until completion when poll is true', async () => {
    process.env.JULES_API_KEY = 'test-key';

    let fetchCount = 0;
    vi.mocked(global.fetch).mockImplementation(async () => {
      fetchCount++;
      return {
        ok: true,
        json: async () => ({
          name: 'sessions/12345',
          state: fetchCount === 1 ? 'IN_PROGRESS' : 'SUCCEEDED',
        }),
      } as any;
    });

    const res = await checkJulesStatus({
      sessionId: '12345',
      poll: true,
      intervalMs: 10,
      timeoutMs: 1000,
    });

    expect(res.status).toBe('COMPLETED');
    expect(res.completed).toBe(true);
    expect(fetchCount).toBe(2);
  });

  it('returns TIMED_OUT when polling times out before completion', async () => {
    process.env.JULES_API_KEY = 'test-key';

    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        name: 'sessions/12345',
        state: 'IN_PROGRESS',
      }),
    } as any);

    const res = await checkJulesStatus({
      sessionId: '12345',
      poll: true,
      intervalMs: 10,
      timeoutMs: 30,
    });

    expect(res.status).toBe('TIMED_OUT');
    expect(res.completed).toBe(false);
  });
});
