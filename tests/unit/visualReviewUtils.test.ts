import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { countExistingReviews, getPreviousReviewState } from '../../lib/visualReviewUtils';

describe('visualReviewUtils - countExistingReviews and getPreviousReviewState', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    vi.restoreAllMocks();
    process.env = {
      ...originalEnv,
      GITHUB_TOKEN: 'mock-token',
      GITHUB_REPOSITORY: 'arii/boomtick',
      PR_NUMBER: '819',
    };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  describe('countExistingReviews', () => {
    it('aggregates counts from both issue comments and PR reviews', async () => {
      const fetchSpy = vi.spyOn(global, 'fetch').mockImplementation(async (url: any) => {
        const urlStr = String(url);
        if (urlStr.includes('/issues/819/comments')) {
          return new Response(
            JSON.stringify([
              {
                body: '## Code Review\n<!-- ai-review-count: 3 -->',
                user: { type: 'Bot' },
              },
            ]),
            { status: 200 }
          );
        }
        if (urlStr.includes('/pulls/819/reviews')) {
          return new Response(
            JSON.stringify([
              {
                body: '## Code Review\n<!-- ai-review-count: 70 -->',
                user: { type: 'Bot' },
              },
            ]),
            { status: 200 }
          );
        }
        return new Response('[]', { status: 200 });
      });

      const total = await countExistingReviews(['Code Review']);
      expect(total).toBe(73);
      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });

    it('returns 0 if env variables are missing', async () => {
      delete process.env.GITHUB_TOKEN;
      const total = await countExistingReviews(['Code Review']);
      expect(total).toBe(0);
    });
  });

  describe('getPreviousReviewState', () => {
    it('extracts state from PR reviews if latest matching state is in PR reviews', async () => {
      const mockState = { findings: [{ id: '1', issue: 'test issue', status: 'open' }] };
      const base64State = Buffer.from(JSON.stringify(mockState)).toString('base64');

      vi.spyOn(global, 'fetch').mockImplementation(async (url: any) => {
        const urlStr = String(url);
        if (urlStr.includes('/issues/819/comments')) {
          return new Response(
            JSON.stringify([
              {
                body: '## Code Review\nOld comment without state',
                user: { type: 'Bot' },
              },
            ]),
            { status: 200 }
          );
        }
        if (urlStr.includes('/pulls/819/reviews')) {
          return new Response(
            JSON.stringify([
              {
                body: `## Code Review\n<!-- ai-review-state: ${base64State} -->`,
                user: { type: 'Bot' },
              },
            ]),
            { status: 200 }
          );
        }
        return new Response('[]', { status: 200 });
      });

      const state = await getPreviousReviewState<{ findings: any[] }>('Code Review');
      expect(state).toEqual(mockState);
    });

    it('returns undefined if no state tag exists in comments or PR reviews', async () => {
      vi.spyOn(global, 'fetch').mockImplementation(async () => {
        return new Response(JSON.stringify([]), { status: 200 });
      });

      const state = await getPreviousReviewState('Code Review');
      expect(state).toBeUndefined();
    });
  });
});
