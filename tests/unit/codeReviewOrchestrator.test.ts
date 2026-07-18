import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { reconcileVerdict, fetchPRGoal, clearCachedPRGoal, formatLinkedIssues } from '../../lib/codeReviewOrchestrator';

import { IMPACT_CONFIG } from '../../scripts/impact-analysis.config';
import { filterLowImpactFiles } from '../../lib/codeReviewUtils';

describe('filtering logic', () => {
  function filterFiles(files: string[]) {
    return filterLowImpactFiles(files, IMPACT_CONFIG.LOW_IMPACT_PATHS);
  }

  it('filters out exact file matches', () => {
    const files = ['pnpm-lock.yaml', 'src/App.tsx'];
    const filtered = filterFiles(files);
    expect(filtered).toEqual(['src/App.tsx']);
  });

  it('filters out directory prefix matches', () => {
    const files = ['dist/index.js', 'src/App.tsx'];
    const filtered = filterFiles(files);
    expect(filtered).toEqual(['src/App.tsx']);
  });

  it('filters out files in nested directories', () => {
    const files = ['dist/subdir/index.js', 'src/App.tsx'];
    const filtered = filterFiles(files);
    expect(filtered).toEqual(['src/App.tsx']);
  });

  it('does not filter out partial name matches that are not directory matches', () => {
    const files = ['distribute.ts', 'src/App.tsx'];
    const filtered = filterFiles(files);
    expect(filtered).toEqual(['distribute.ts', 'src/App.tsx']);
  });

  it('filters out files with directory name matches inside other directories', () => {
    const files = ['src/dist/index.js', 'src/App.tsx'];
    const filtered = filterFiles(files);
    expect(filtered).toEqual(['src/App.tsx']);
  });

  it('handles empty or malformed low impact paths gracefully', () => {
    const files = ['dist/index.js', 'src/App.tsx'];
    expect(filterLowImpactFiles(files, [])).toEqual(files);

    // Test validation
    expect(() => filterLowImpactFiles(files, null as unknown as string[])).toThrow(TypeError);
    expect(() => filterLowImpactFiles(undefined as unknown as string[], [])).toThrow(TypeError);
  });

  it('does not filter out exact file matches with suffixes', () => {
    const files = ['pnpm-lock.yaml.bak', 'src/App.tsx'];
    const filtered = filterFiles(files);
    expect(filtered).toEqual(['pnpm-lock.yaml.bak', 'src/App.tsx']);
  });

  it('filters out nested directory prefix matches', () => {
    const files = ['packages/web/dist/index.js', 'src/App.tsx'];
    const filtered = filterFiles(files);
    expect(filtered).toEqual(['src/App.tsx']);
  });

  it('filters out nested file matches', () => {
    const files = ['packages/web/pnpm-lock.yaml', 'src/App.tsx'];
    const filtered = filterFiles(files);
    expect(filtered).toEqual(['src/App.tsx']);
  });
});

describe('reconcileVerdict', () => {
  let consoleWarnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  });

  afterEach(() => {
    if (consoleWarnSpy) {
      consoleWarnSpy.mockRestore();
    }
  });
  it('downgrades fail to warn if no parseable findings', () => {
    const result = reconcileVerdict({ feedback: '', llmVerdict: 'fail', tokens: 0, cost: 0 }, '');
    expect(result.llmVerdict).toBe('warn');
    expect(consoleWarnSpy).toHaveBeenCalledWith(expect.stringContaining('Downgrading FAIL→WARN: no open findings found to justify the FAIL verdict.'));
  });

  it('respects open findings', () => {
    const result = reconcileVerdict(
      {
        feedback: '', llmVerdict: 'fail', tokens: 0, cost: 0,
        state: {
          findings: [
            { id: '1', file: 'f', issue: 'test', snippet: 'const a = 1;', status: 'open' }
          ]
        }
      },
      ''
    );
    expect(result.llmVerdict).toBe('fail');
  });

  it('downgrades fail to warn if all findings are resolved', () => {
    const result = reconcileVerdict(
      {
        feedback: '', llmVerdict: 'fail', tokens: 0, cost: 0,
        state: {
          findings: [
            { id: '1', file: 'f', issue: 'test', snippet: 'const a = 1;', status: 'resolved' }
          ]
        }
      },
      ''
    );
    expect(result.llmVerdict).toBe('warn');
    expect(consoleWarnSpy).toHaveBeenCalledWith(expect.stringContaining('Downgrading FAIL→WARN: no open findings found to justify the FAIL verdict.'));
  });
});

describe('fetchPRGoal', () => {
  const originalEnv = { ...process.env };

  beforeEach(() => {
    process.env = {
      ...originalEnv,
      GITHUB_TOKEN: 'fake-token',
      GITHUB_REPOSITORY: 'arii/tech-dancer',
      PR_NUMBER: '42',
    };
    clearCachedPRGoal();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it('returns undefined if environment variables are missing', async () => {
    delete process.env.GITHUB_TOKEN;
    const res = await fetchPRGoal();
    expect(res).toBeUndefined();
  });

  it('queries GraphQL successfully with no linked issues and returns title and body', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        data: {
          repository: {
            pullRequest: {
              title: 'My PR Title',
              body: 'My PR Body',
              closingIssuesReferences: {
                nodes: []
              }
            }
          }
        }
      })
    } as Response);

    const res = await fetchPRGoal();
    expect(res).toBe('My PR Title\n\nMy PR Body');
    expect(fetchSpy).toHaveBeenCalledWith('https://api.github.com/graphql', expect.any(Object));
  });

  it('queries GraphQL successfully with linked issues and returns enriched context', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        data: {
          repository: {
            pullRequest: {
              title: 'Implement feature X',
              body: 'Closes #123',
              closingIssuesReferences: {
                nodes: [
                  {
                    number: 123,
                    title: 'Issue 123 Title',
                    body: 'Issue 123 Body',
                    labels: {
                      nodes: [
                        { name: 'spec-driven' },
                        { name: 'bug' }
                      ]
                    }
                  }
                ]
              }
            }
          }
        }
      })
    } as Response);

    const res = await fetchPRGoal();
    expect(res).toContain('Implement feature X\n\nCloses #123');
    expect(res).toContain('LINKED ISSUE arii/tech-dancer#123 SPECIFICATION:');
    expect(res).toContain('Title: Issue 123 Title');
    expect(res).toContain('Labels: [spec-driven, bug]');
    expect(res).toContain('Description:\nIssue 123 Body');
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it('falls back to REST API if GraphQL fetch throws or is not ok', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error'
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          title: 'REST PR Title',
          body: 'REST PR Body'
        })
      } as Response);

    const res = await fetchPRGoal();
    expect(res).toBe('REST PR Title\n\nREST PR Body');
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(fetchSpy).toHaveBeenNthCalledWith(1, 'https://api.github.com/graphql', expect.any(Object));
    expect(fetchSpy).toHaveBeenNthCalledWith(2, 'https://api.github.com/repos/arii/tech-dancer/pulls/42', expect.any(Object));
  });

  it('falls back to REST API if GraphQL response has payload.errors', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          errors: [{ message: 'Some GraphQL error' }]
        })
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          title: 'REST PR Title 2',
          body: 'REST PR Body 2'
        })
      } as Response);

    const res = await fetchPRGoal();
    expect(res).toBe('REST PR Title 2\n\nREST PR Body 2');
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  it('correctly formats linked issues using the formatLinkedIssues helper', () => {
    const issues = [
      {
        number: 101,
        title: 'Crash on startup',
        body: 'Details about crash',
        labels: {
          nodes: [{ name: 'critical' }, { name: 'bug' }]
        }
      }
    ];
    const formatted = formatLinkedIssues(issues, 'owner/repo');
    expect(formatted).toBe(
      'LINKED ISSUE owner/repo#101 SPECIFICATION:\n' +
      'Title: Crash on startup\n' +
      'Labels: [critical, bug]\n' +
      'Description:\n' +
      'Details about crash'
    );
  });
});
