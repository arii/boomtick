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

  it('fails incomplete execution and reports the skip reason', () => {
    const r = evaluateVerdictGate({ llmVerdict: 'warn', skipReason: 'TRUNCATED' }, { failOnVerdict: true });
    expect(r.shouldFail).toBe(true);
    expect(r.message).toContain('TRUNCATED');
  });

  it('fails a missing verdict loudly', () => {
    const r = evaluateVerdictGate(undefined, { failOnVerdict: true });
    expect(r.verdict).toBe('unknown');
    expect(r.shouldFail).toBe(true);
    expect(r.message).toContain('MISSING_OR_INVALID_VERDICT');
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

describe('execution failures are not policy verdicts', () => {
  it.each(['RATE_LIMIT', 'MISSING_API_KEY', 'UNHANDLED_ERROR', 'PARSE_ERROR', 'TRUNCATED'])(
    'fails %s even with the findings gate disabled', skipReason => {
      const result = evaluateVerdictGate({ llmVerdict: 'warn', skipReason }, { failOnVerdict: false });
      expect(result.shouldFail).toBe(true);
      expect(result.message).toContain(skipReason);
      expect(result.message).toContain('No completed review');
    }
  );
  it('leaves an actual completed warning nonblocking', () => {
    expect(evaluateVerdictGate({ llmVerdict: 'warn' }, { failOnVerdict: true }).shouldFail).toBe(false);
  });
});

describe('untrusted finding text', () => {
  const evil = {
    llmVerdict: 'fail',
    skipReason: 'x\n::add-mask::s',
    state: {
      findings: [
        { status: 'open', severity: 'HIGH', file: 'a.ts\n::stop-commands::tok', line: 1, issue: 'bad\r\n::add-mask::secret\n::error::boom <b>x</b>' },
      ],
    },
  };

  it('keeps every finding on one line so no stderr line starts a workflow command', () => {
    const r = evaluateVerdictGate(evil as any, { failOnVerdict: true });
    for (const line of r.message.split('\n')) expect(line.startsWith('::')).toBe(false);
    expect(r.message.split('\n')).toHaveLength(2);
  });

  it('writes sanitized text to stderr, the summary and the output', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gate-evil-'));
    const out = path.join(dir, 'out');
    const sum = path.join(dir, 'sum');
    const err = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const log = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const prev = process.exitCode;
    try {
      publishVerdictGate(evaluateVerdictGate(evil as any, { failOnVerdict: true }), { GITHUB_OUTPUT: out, GITHUB_STEP_SUMMARY: sum });
      const stderr = String(err.mock.calls[0][0]);
      for (const line of stderr.split('\n')) expect(line.startsWith('::')).toBe(false);
      expect(fs.readFileSync(sum, 'utf8')).not.toContain('<b>');
      for (const line of fs.readFileSync(sum, 'utf8').split('\n')) expect(line.startsWith('::')).toBe(false);
    } finally {
      err.mockRestore();
      log.mockRestore();
      process.exitCode = prev;
    }
  });

  it('does not interpret injected text as an execution reason', () => {
    const r = evaluateVerdictGate({ llmVerdict: 'warn', skipReason: 'RATE_LIMIT\n::add-mask::s' }, { failOnVerdict: true });
    expect(r.shouldFail).toBe(false);
    expect(r.message.split('\n')).toHaveLength(1);
    expect(r.summaryMarkdown).toContain('RATE');
    expect(r.summaryMarkdown).toContain('does not fail this check');
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
    expect(annotation.startsWith('::error title=AI review failure::')).toBe(true);
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


describe('container smoke contract', () => {
  it('tests missing-key failure without network and never sends a fake provider key', () => {
    const workflow = fs.readFileSync(new URL('../../.github/workflows/smoke-test-impact-analysis.yml', import.meta.url), 'utf8');
    expect(workflow).toContain('docker run --rm --network none');
    expect(workflow).toContain('test "$status" -eq 1');
    expect(workflow).toContain('.passed == false and .skipReason == "MISSING_API_KEY"');
    expect(workflow).not.toContain('gemini_api_key: "MOCK_KEY"');
  });
});
