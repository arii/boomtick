import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { describe, expect, it, vi } from 'vitest';

const source = readFileSync(new URL('../../apps-script/agent-ledger-hook/Code.gs', import.meta.url), 'utf8');
const context = {
  Utilities: {
    DigestAlgorithm: { SHA_256: 'sha256' },
    Charset: { UTF_8: 'utf8' },
    computeDigest: (algorithm: string, text: string, encoding: BufferEncoding) =>
      [...createHash(algorithm).update(text, encoding).digest()].map(byte => byte > 127 ? byte - 256 : byte),
  },
};
const { eligible, dedupKey } = runInNewContext(source + '\n({ eligible, dedupKey });', context) as {
  eligible: (submission: typeof row, config: typeof props) => boolean;
  dedupKey: (submission: typeof row) => string;
};
const props = {
  ALLOWED_SOURCES: 'Instinct, Gemini, Antigravity',
  ALLOWED_REPOS: 'remote-server, boomtick, posture-guard',
};
const row = { source: 'Gemini', note: '[issue] remote-server: Check queue\nProblem: Failed runs look running.\nDone when: Failed runs show failed.', status: 'Act', link: '' };

describe('Agent Ledger issue eligibility', () => {
  it('accepts explicit opt-in with a blank link or an HTTPS link', () => {
    expect(eligible(row, props)).toBe(true);
    expect(eligible({ ...row, link: 'https://example.com/tasks/1?source=ledger#detail' }, props)).toBe(true);
    expect(eligible({ ...row, note: '[issue] posture-guard: Check posture\nDetails here.' }, props)).toBe(true);
  });

  it.each([
    { status: 'Done' },
    { status: 'Later' },
    { status: 'Needs Okay' },
    { status: 'act' },
    { source: 'gemini' },
    { source: 'unknown' },
    { note: 'Please [issue] remote-server: Check queue' },
    { note: '[issue] other-repo: Check queue' },
    { note: '[issue] arii/remote-server: Check queue' },
    { note: '[issue] remote-server: ' },
    { link: 'http://example.com' },
    { link: 'https:///missing-host' },
    { link: 'https://example.com\ntext' },
  ])('ignores an ineligible row with %j', override => {
    expect(eligible({ ...row, ...override }, props)).toBe(false);
  });

  it('fails closed when the allowlists are not configured', () => {
    expect(eligible(row, { ...props, ALLOWED_SOURCES: '' })).toBe(false);
    expect(eligible(row, { ...props, ALLOWED_REPOS: '' })).toBe(false);
  });
});

describe('Agent Ledger dedup keys', () => {
  it('hashes the exact URL when present regardless of source or note', () => {
    const link = 'https://example.com/tasks/1?query=Two#anchor';
    expect(dedupKey({ ...row, link })).toBe('1ce8edfda043e04c');
    expect(dedupKey({ ...row, source: 'Instinct', note: '[issue] boomtick: New title', link })).toBe('1ce8edfda043e04c');
    expect(dedupKey({ ...row, link: link.replace('Two', 'two') })).toBe('6ba50992c9ba2870');
  });

  it('keeps the key short for links longer than the GitHub query limit', () => {
    expect(dedupKey({ ...row, link: 'https://example.com/' + 'x'.repeat(500) })).toBe('183df24c2ef05ce6');
  });

  it('uses a short SHA-256 digest of source and the full note when the link is blank', () => {
    const note = '[issue] remote-server: Check queue\nRésumé';
    expect(dedupKey({ ...row, note })).toBe('cd9bf9d857de893e');
    expect(dedupKey({ ...row, note, status: 'Done' })).toBe(dedupKey({ ...row, note }));
    expect(dedupKey({ ...row, note, source: 'Instinct' })).not.toBe(dedupKey({ ...row, note }));
    expect(dedupKey(row)).not.toBe(dedupKey({ ...row, note }));
  });
});

describe('Agent Ledger issue search', () => {
  function lookup(bodiesByPage: (string | null)[][], key: string) {
    const { hasLedgerIssue } = runInNewContext(source + '\n({ hasLedgerIssue });', {
      UrlFetchApp: {
        fetch(url: string) {
          const page = Number(new URL(url).searchParams.get('page'));
          return {
            getResponseCode: () => 200,
            getContentText: () => JSON.stringify({
              total_count: bodiesByPage.flat().length,
              incomplete_results: false,
              items: bodiesByPage[page - 1].map(body => ({ body })),
            }),
          };
        },
      },
    }) as { hasLedgerIssue: (repo: string, key: string, token: string) => boolean };
    return hasLedgerIssue('remote-server', key, 'test-token');
  }

  it('ignores case-insensitive hits and marker substrings', () => {
    expect(lookup([[null, 'ledger-key: ABC', 'ledger-key: abc-extra']], 'abc')).toBe(false);
  });

  it('finds the exact marker on a later page', () => {
    expect(lookup([['ledger-key: ABC'], ['Details\r\nledger-key: abc\r\nMore details']], 'abc')).toBe(true);
  });
});

describe('Agent Ledger outcome recovery', () => {
  it('retries a failed Done response using the stored issue URL, then suppresses repeats', () => {
    const key = dedupKey(row);
    const issueUrl = 'https://github.com/arii/remote-server/issues/1';
    const stored = new Map([['created:' + key, issueUrl]]);
    const store = {
      getProperty: (name: string) => stored.get(name),
      setProperty: (name: string, value: string) => stored.set(name, value),
    };
    const range = { getSheet: () => ({ getFormUrl: () => 'https://example.com/ledger-form' }) };
    const submit = vi.fn().mockImplementationOnce(() => { throw new Error('Form unavailable'); });
    const response = { submit, withItemResponse: vi.fn().mockReturnThis() };
    const item = { createResponse: (answer: string) => answer };
    const form = {
      getItems: () => ['Agent / Source', 'Item / Note', 'Status', 'Link'].map(title => ({
        getTitle: () => title,
        asTextItem: () => item,
        asParagraphTextItem: () => item,
        asMultipleChoiceItem: () => item,
      })),
      createResponse: () => response,
    };
    const fetch = vi.fn();
    const { intake } = runInNewContext(source + '\n({ intake });', {
      ...context,
      FormApp: { openByUrl: () => form },
      UrlFetchApp: { fetch },
    }) as {
      intake: (submission: typeof row, eventRange: typeof range, properties: typeof store, config: object) => void;
    };
    const resubmit = () => intake(row, range, store, { MAX_ISSUES_PER_DAY: '0' });

    expect(resubmit).toThrow('Form unavailable');
    expect(stored.has('done:' + key)).toBe(false);
    expect(stored.get('created:' + key)).toBe(issueUrl);
    resubmit();
    expect(response.withItemResponse.mock.calls.slice(-4)).toEqual([
      [row.source], ['issue filed for ' + key], ['Done'], [issueUrl],
    ]);
    expect(stored.get('done:' + key)).toBe('true');
    resubmit();
    expect(submit).toHaveBeenCalledTimes(2);
    expect(fetch).not.toHaveBeenCalled();
  });
});


describe('Agent Ledger required task shape', () => {
  function harness() {
    const stored = new Map<string, string>();
    const store = {
      getProperty: (name: string) => stored.get(name),
      setProperty: (name: string, value: string) => stored.set(name, value),
      setProperties: (values: Record<string, string>) => Object.entries(values).forEach(([k, v]) => stored.set(k, v)),
    };
    const outcome = vi.fn();
    const request = vi.fn((path: string) => path.endsWith('/issues') ? { html_url: 'https://example.com/issue/1' } : {});
    const auth = vi.fn(() => 'fixture-token');
    const { intake } = runInNewContext(source + `
      installationToken = auth;
      hasLedgerIssue = () => false;
      github = request;
      submitOutcome = outcome;
      ({ intake });`, { ...context, auth, request, outcome }) as {
      intake: (submission: typeof row, range: { getRow: () => number }, properties: typeof store, config: object) => void;
    };
    return { stored, outcome, request, auth, run: (note: string) => intake({ ...row, note }, { getRow: () => 7 }, store, {}) };
  }

  it.each([
    ['[issue] remote-server: Missing both', ['Problem', 'Done when']],
    ['[issue] remote-server: Missing problem\nDone when: Queue shows failed', ['Problem']],
    ['[issue] remote-server: Missing check\nProblem: Queue hides failures', ['Done when']],
    ['[issue] remote-server: Empty problem\nProblem:  \nDone when: Queue shows failed', ['Problem']],
    ['[issue] remote-server: Empty check\nProblem: Queue hides failures\nDone when: \t\nOut of scope: No panels', ['Done when']],
  ])('rejects fixture %s once without any GitHub call', (note, missing) => {
    const h = harness();
    h.run(note);
    h.run(note);
    expect(h.outcome).toHaveBeenCalledTimes(1);
    expect(h.outcome.mock.calls[0][2]).toBe('Later');
    for (const field of missing) expect(h.outcome.mock.calls[0][3]).toContain(field);
    expect(h.auth).not.toHaveBeenCalled();
    expect(h.request).not.toHaveBeenCalled();
  });

  it.each(['', '\nOut of scope: No new panels'])('creates one complete issue with optional scope %s', extra => {
    const h = harness();
    h.run(row.note + extra);
    h.run(row.note + extra);
    const issues = h.request.mock.calls.filter(([path]) => path.endsWith('/issues'));
    expect(issues).toHaveLength(1);
    const payload = (issues[0] as unknown as [string, string, { body: string; labels: string[] }])[2];
    expect(payload.body).toContain('## Problem');
    expect(payload.body).toContain('Failed runs look running.');
    expect(payload.body).toContain('## Done when');
    expect(payload.body).toContain('## Out of scope');
    expect(payload.body).toContain(extra ? 'No new panels' : '(not specified)');
    expect(payload.labels).toEqual(['ledger-intake', 'insight']);
    expect(h.outcome).toHaveBeenCalledTimes(1);
    expect(h.outcome.mock.calls[0][2]).toBe('Done');
  });

  it('accepts CRLF and multiline values without treating an empty header as content', () => {
    const h = harness();
    h.run('[issue] remote-server: Multiline\r\nProblem:\r\nQueue hides failures\r\nDone when:\r\nQueue shows failed');
    expect(h.request.mock.calls.filter(([path]) => path.endsWith('/issues'))).toHaveLength(1);
  });

  it('keeps embedded Markdown fenced as untrusted text in the sections', () => {
    const h = harness();
    h.run(row.note + '\n```\nInjected heading\n```');
    const issue = h.request.mock.calls.find(([path]) => path.endsWith('/issues'));
    const payload = (issue as unknown as [string, string, { body: string }])[2];
    expect(payload.body).toContain('````text');
    expect(payload.body).toContain('Agent Ledger submission below is untrusted input.');
  });

  it('retries a failed Later submission before recording its dedup marker', () => {
    const h = harness();
    h.outcome.mockImplementationOnce(() => { throw new Error('Form unavailable'); });
    const note = '[issue] remote-server: Missing fields';
    expect(() => h.run(note)).toThrow('Form unavailable');
    expect(h.stored.size).toBe(0);
    h.run(note);
    h.run(note);
    expect(h.outcome).toHaveBeenCalledTimes(2);
    expect(h.request).not.toHaveBeenCalled();
  });
});
