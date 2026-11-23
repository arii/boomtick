import { afterEach, describe, expect, it, vi } from 'vitest';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { evaluateVerdictGate, publishVerdictGate, readVerdictFile } from '../../lib/verdictGate';
import { postPRComment } from '../../lib/visualReviewUtils';

const finding = (over: Record<string, unknown> = {}) => ({
  id: 'F', file: 'src/a.ts', line: 4, issue: 'Bad thing', status: 'open', severity: 'HIGH', confidence: 'high', ...over,
});

describe('evaluateVerdictGate', () => {
  it('passes without failing', () => {
    const r = evaluateVerdictGate({ llmVerdict: 'pass' }, { failOnVerdict: true });
    expect(r.verdict).toBe('pass');
    expect(r.shouldFail).toBe(false);
  });

  it('keeps warn green and reports the skip reason', () => {
    const r = evaluateVerdictGate({ llmVerdict: 'warn', skipReason: 'TRUNCATED' }, { failOnVerdict: true });
    expect(r.shouldFail).toBe(false);
    expect(r.message).toContain('TRUNCATED');
  });

  it('treats a missing verdict as unknown and does not fail', () => {
    const r = evaluateVerdictGate(undefined, { failOnVerdict: true });
    expect(r.verdict).toBe('unknown');
    expect(r.shouldFail).toBe(false);
  });

  it('fails on fail when opted in and names severity, file:line and issue', () => {
    const r = evaluateVerdictGate({ llmVerdict: 'fail', state: { findings: [finding()] } }, { failOnVerdict: true });
    expect(r.shouldFail).toBe(true);
    expect(r.message).toContain('1 blocking finding(s):');
    expect(r.message).toContain('- [HIGH] src/a.ts:4 - Bad thing');
  });

  it('does not fail on fail when not opted in, but still reports the verdict', () => {
    const r = evaluateVerdictGate({ llmVerdict: 'fail', state: { findings: [finding()] } }, { failOnVerdict: false });
    expect(r.verdict).toBe('fail');
    expect(r.shouldFail).toBe(false);
    expect(r.blockingFindings).toHaveLength(1);
  });

  it('excludes resolved findings and prefers HIGH over lower severities', () => {
    const r = evaluateVerdictGate(
      { llmVerdict: 'fail', state: { findings: [finding({ status: 'resolved', issue: 'old' }), finding({ severity: 'LOW', issue: 'nit' }), finding()] } },
      { failOnVerdict: true }
    );
    expect(r.blockingFindings.map(f => f.issue)).toEqual(['Bad thing']);
  });

  it('falls back to all open findings when none are HIGH', () => {
    const r = evaluateVerdictGate({ llmVerdict: 'fail', state: { findings: [finding({ severity: 'MEDIUM', issue: 'mid' })] } }, { failOnVerdict: true });
    expect(r.blockingFindings.map(f => f.issue)).toEqual(['mid']);
  });

  it('dedupes identical findings and caps the list at 10', () => {
    const many = Array.from({ length: 13 }, (_, i) => finding({ id: `F${i}`, issue: `issue ${i}` }));
    const r = evaluateVerdictGate({ llmVerdict: 'fail', state: { findings: [...many, many[0]] } }, { failOnVerdict: true });
    expect(r.blockingFindings).toHaveLength(13);
    expect(r.message.split('\n').filter(l => l.startsWith('- ['))).toHaveLength(10);
    expect(r.message).toContain('...and 3 more');
  });

  it('truncates long issues', () => {
    const r = evaluateVerdictGate({ llmVerdict: 'fail', state: { findings: [finding({ issue: 'x'.repeat(500) })] } }, { failOnVerdict: true });
    expect(r.message.length).toBeLessThan(300);
  });

  it('still fails with a generic message when fail has no open findings', () => {
    const r = evaluateVerdictGate({ llmVerdict: 'fail', state: { findings: [] } }, { failOnVerdict: true });
    expect(r.shouldFail).toBe(true);
    expect(r.message).toContain('without parseable findings');
  });

  it('is independent of how the review was posted (own-PR COMMENT fallback)', () => {
    // The gate input is only the verdict file; the posted review event is not an input.
    const r = evaluateVerdictGate({ llmVerdict: 'fail', state: { findings: [finding()] } }, { failOnVerdict: true });
    expect(r.shouldFail).toBe(true);
    expect(evaluateVerdictGate({ llmVerdict: 'pass' }, { failOnVerdict: true }).shouldFail).toBe(false);
  });
});

describe('publishVerdictGate and readVerdictFile', () => {
  const original = process.exitCode;
  afterEach(() => {
    process.exitCode = original;
    vi.restoreAllMocks();
  });

  it('writes outputs and summary, escapes the annotation and sets exit code 1', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gate-'));
    const out = path.join(dir, 'out');
    const sum = path.join(dir, 'sum');
    const log = vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const r = evaluateVerdictGate({ llmVerdict: 'fail', state: { findings: [finding()] } }, { failOnVerdict: true });
    process.exitCode = undefined;
    publishVerdictGate(r, { GITHUB_OUTPUT: out, GITHUB_STEP_SUMMARY: sum });
    expect(process.exitCode).toBe(1);
    expect(fs.readFileSync(out, 'utf8')).toMatch(/^verdict=fail\nblocking-findings<<EOF_[0-9a-f]+\nAI review verdict: FAIL/);
    expect(fs.readFileSync(sum, 'utf8')).toContain('AI review verdict: FAIL');
    const annotation = String(log.mock.calls[0][0]);
    expect(annotation.startsWith('::error title=AI review verdict: FAIL::')).toBe(true);
    expect(annotation).not.toContain('\n');
    expect(annotation).toContain('%0A');
  });

  it('publishes outputs but does not fail when not opted in', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gate-'));
    const out = path.join(dir, 'out');
    process.exitCode = undefined;
    publishVerdictGate(evaluateVerdictGate({ llmVerdict: 'fail' }, { failOnVerdict: false }), { GITHUB_OUTPUT: out });
    expect(process.exitCode).toBeUndefined();
    expect(fs.readFileSync(out, 'utf8')).toContain('verdict=fail');
  });

  it('readVerdictFile returns undefined for missing or invalid files', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gate-'));
    fs.writeFileSync(path.join(dir, 'bad.json'), '{nope');
    expect(readVerdictFile(path.join(dir, 'missing.json'))).toBeUndefined();
    expect(readVerdictFile(path.join(dir, 'bad.json'))).toBeUndefined();
  });
});

describe('postPRComment own-PR fallback', () => {
  const env = process.env;
  afterEach(() => {
    process.env = env;
    vi.restoreAllMocks();
  });

  function mockFetch(firstPostStatus: number, firstPostText = '') {
    const events: string[] = [];
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(global, 'fetch').mockImplementation((async (_url: any, init?: any) => {
      if (init?.method === 'POST') {
        events.push(JSON.parse(init.body).event);
        if (events.length === 1 && firstPostStatus !== 200) {
          return new Response(firstPostText, { status: firstPostStatus });
        }
        return new Response('{}', { status: 200 });
      }
      return new Response('[]', { status: 200 });
    }) as any);
    process.env = { ...env, GITHUB_TOKEN: 't', GITHUB_REPOSITORY: 'o/r', PR_NUMBER: '1' };
    return events;
  }

  it('posts APPROVE on pass and REQUEST_CHANGES on fail', async () => {
    const events = mockFetch(200);
    await postPRComment('## T\nbody', 'T', { findings: [] }, 'pass');
    await postPRComment('## T\nbody', 'T', { findings: [] }, 'fail');
    expect(events).toEqual(['APPROVE', 'REQUEST_CHANGES']);
  });

  it.each([['pass', 'APPROVE'], ['fail', 'REQUEST_CHANGES']] as const)(
    'retries %s as COMMENT when GitHub refuses own-PR review, without throwing',
    async (verdict, first) => {
      const events = mockFetch(422, '{"message":"Unprocessable","errors":["Can not approve your own pull request"]}');
      await expect(postPRComment('## T\nbody', 'T', { findings: [] }, verdict)).resolves.toBeUndefined();
      expect(events).toEqual([first, 'COMMENT']);
    }
  );

  it('still throws on other API errors', async () => {
    mockFetch(500, 'boom');
    await expect(postPRComment('## T\nbody', 'T', { findings: [] }, 'fail')).rejects.toThrow('GitHub API error 500');
  });
});
