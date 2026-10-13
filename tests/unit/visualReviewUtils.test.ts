import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { countExistingReviews, getPreviousReviewState, generateMarkdownReport } from '../../lib/visualReviewUtils';

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
    it('takes max review count per report title across comments and PR reviews to avoid double-counting', async () => {
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
                body: '## Code Review\n<!-- ai-review-count: 5 -->',
                user: { type: 'Bot' },
              },
            ]),
            { status: 200 }
          );
        }
        return new Response('[]', { status: 200 });
      });

      const total = await countExistingReviews(['Code Review']);
      // Max count for 'Code Review' is 5 (from reviews), NOT 3 + 5 = 8
      expect(total).toBe(5);
      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });

    it('sums max counts for distinct report titles', async () => {
      vi.spyOn(global, 'fetch').mockImplementation(async (url: any) => {
        const urlStr = String(url);
        if (urlStr.includes('/issues/819/comments')) {
          return new Response(
            JSON.stringify([
              {
                body: '## Gemini Code Review\n<!-- ai-review-count: 2 -->',
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
                body: '## GitHub Models Code Review\n<!-- ai-review-count: 4 -->',
                user: { type: 'Bot' },
              },
            ]),
            { status: 200 }
          );
        }
        return new Response('[]', { status: 200 });
      });

      const total = await countExistingReviews(['Gemini Code Review', 'GitHub Models Code Review']);
      expect(total).toBe(6);
    });

    it('returns 0 if env variables are missing', async () => {
      delete process.env.GITHUB_TOKEN;
      const total = await countExistingReviews(['Code Review']);
      expect(total).toBe(0);
    });
  });

  describe('getPreviousReviewState', () => {
    it('extracts latest state tag sorted by timestamp descending', async () => {
      const oldState = { findings: [{ id: 'old', status: 'open' }] };
      const newState = { findings: [{ id: 'new', status: 'resolved' }] };

      const oldBase64 = Buffer.from(JSON.stringify(oldState)).toString('base64');
      const newBase64 = Buffer.from(JSON.stringify(newState)).toString('base64');

      vi.spyOn(global, 'fetch').mockImplementation(async (url: any) => {
        const urlStr = String(url);
        if (urlStr.includes('/issues/819/comments')) {
          return new Response(
            JSON.stringify([
              {
                body: `## Code Review\n<!-- ai-review-state: ${newBase64} -->`,
                user: { type: 'Bot' },
                created_at: '2026-10-13T20:00:00Z',
              },
            ]),
            { status: 200 }
          );
        }
        if (urlStr.includes('/pulls/819/reviews')) {
          return new Response(
            JSON.stringify([
              {
                body: `## Code Review\n<!-- ai-review-state: ${oldBase64} -->`,
                user: { type: 'Bot' },
                submitted_at: '2026-10-13T10:00:00Z',
              },
            ]),
            { status: 200 }
          );
        }
        return new Response('[]', { status: 200 });
      });

      const state = await getPreviousReviewState<{ findings: any[] }>('Code Review');
      expect(state).toEqual(newState);
    });

    it('returns undefined if no state tag exists in comments or PR reviews', async () => {
      vi.spyOn(global, 'fetch').mockImplementation(async () => {
        return new Response(JSON.stringify([]), { status: 200 });
      });

      const state = await getPreviousReviewState('Code Review');
      expect(state).toBeUndefined();
    });
  });

  describe('generateMarkdownReport', () => {
    it('renders Review Iteration when iteration parameter is passed', () => {
      const report = generateMarkdownReport(
        [
          {
            route: '/home',
            severity: 'LOW',
            differencePercent: 0.5,
            feedback: 'Looks good',
            tokens: 100,
            cost: 0.001,
            modelName: 'gpt-4o',
          },
        ],
        'VisualBot',
        'Visual Review',
        'Visual Tagline',
        2
      );

      expect(report).toContain('## Visual Review');
      expect(report).toContain('**Review Iteration:** #2 of 10');
      expect(report).toContain('**Summary:** 🔴 0 high · 🟡 0 medium · 🟢 1 low');
    });
  });
});
