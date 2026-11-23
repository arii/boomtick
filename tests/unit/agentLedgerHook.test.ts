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

interface HashVector {
  title: string;
  repo: string;
  normalized_title: string;
  normalized_repo: string;
  dedupe_hash: string;
  intake_id: string;
}
const vectors = (JSON.parse(readFileSync(new URL('../fixtures/agent-ledger/intake-hash-vectors.json', import.meta.url), 'utf8')) as {
  vectors: HashVector[];
}).vectors;

describe('Agent Ledger intake hash matches scripts/ledger_intake.py', () => {
  const load = () => runInNewContext(source + '\n({ normalize, dedupeHash, intakeId });', { ...context }) as {
    normalize: (value: string) => string;
    dedupeHash: (title: string, repo: string) => string;
    intakeId: (title: string, repo: string) => string;
  };

  it('has vectors covering the tricky inputs', () => {
    expect(vectors.length).toBeGreaterThanOrEqual(20);
  });

  it.each(vectors.map(vector => [JSON.stringify(vector.title), vector] as const))('matches Python for title %s', (_name, vector) => {
    const { normalize, dedupeHash, intakeId } = load();
    expect(normalize(vector.title)).toBe(vector.normalized_title);
    expect(normalize(vector.repo)).toBe(vector.normalized_repo);
    expect(dedupeHash(vector.title, vector.repo)).toBe(vector.dedupe_hash);
    expect(dedupeHash(vector.title, vector.repo)).toMatch(/^[0-9a-f]{64}$/);
    expect(intakeId(vector.title, vector.repo)).toBe(vector.intake_id);
  });
});

describe('Agent Ledger submit writes intake columns', () => {
  const HEADERS = ['Timestamp', 'Agent / Source', 'Item / Note', 'Status', 'Link'];
  const sha = (text: string) => createHash('sha256').update(text, 'utf8').digest('hex');
  const config = { ...props, GITHUB_APP_ID: '1' };

  function setup(headers: string[] = HEADERS) {
    const stored = new Map<string, string>();
    const store = {
      getProperty: (name: string) => stored.get(name),
      setProperty: (name: string, value: string) => stored.set(name, value),
      setProperties: (values: Record<string, string>) => Object.entries(values).forEach(([k, v]) => stored.set(k, v)),
      getProperties: () => ({ ...config }),
    };
    const grid: string[][] = [[...headers]];
    const writes: { row: number; col: number; values: string[][] }[] = [];
    const sheet = {
      getLastColumn: () => grid[0].length,
      getRange: (r: number, c: number, nr: number, nc: number) => ({
        getValues: () => Array.from({ length: nr }, (_, i) =>
          Array.from({ length: nc }, (_, j) => (grid[r - 1 + i] || [])[c - 1 + j] ?? '')),
        setValues: (values: string[][]) => {
          writes.push({ row: r, col: c, values });
          values.forEach((line, i) => {
            grid[r - 1 + i] = grid[r - 1 + i] || [];
            line.forEach((value, j) => { grid[r - 1 + i][c - 1 + j] = value; });
          });
        },
      }),
    };
    const outcome = vi.fn();
    const request = vi.fn((path: string) => path.endsWith('/issues') ? { html_url: 'https://example.com/issue/1' } : {});
    const { onFormSubmit } = runInNewContext(source + `
      installationToken = () => 'fixture-token';
      hasLedgerIssue = () => false;
      github = request;
      submitOutcome = outcome;
      ({ onFormSubmit });`, {
      ...context,
      request,
      outcome,
      console: { info: () => undefined },
      PropertiesService: { getScriptProperties: () => store },
      LockService: { getScriptLock: () => ({ waitLock: () => undefined, releaseLock: () => undefined }) },
    }) as { onFormSubmit: (event: object) => void };
    const submit = (note: string, overrides: Record<string, string> = {}) => {
      const rowNumber = grid.length + 1;
      const values: Record<string, string> = { 'Agent / Source': row.source, 'Item / Note': note, Status: 'Act', Link: '', ...overrides };
      grid.push(grid[0].map(name => values[name] ?? ''));
      onFormSubmit({
        namedValues: Object.fromEntries(Object.entries(values).map(([k, v]) => [k, [v]])),
        range: { getRow: () => rowNumber, getSheet: () => sheet },
      });
      return rowNumber;
    };
    const cells = (rowNumber: number) => Object.fromEntries(grid[0].map((name, i) => [name, grid[rowNumber - 1][i]]));
    const issues = () => request.mock.calls.filter(([path]) => path.endsWith('/issues')).length;
    return { grid, writes, submit, cells, issues, outcome, stored };
  }

  const fullHash = sha('check queue\narii/remote-server');

  it('writes NEW with intake_id, dedupe_hash and empty missing_fields for a complete row', () => {
    const h = setup();
    const cells = h.cells(h.submit(row.note));
    expect(cells).toMatchObject({
      intake_id: 'ledger-intake-' + fullHash.slice(0, 24),
      dedupe_hash: fullHash,
      missing_fields: '',
      status: 'NEW',
    });
    expect(h.issues()).toBe(1);
  });

  it('writes NEEDS_INFO with the missing fields CSV in order', () => {
    const h = setup();
    expect(h.cells(h.submit('[issue] remote-server: Check queue\nProblem: Failed runs look running.'))).toMatchObject({
      status: 'NEEDS_INFO', missing_fields: 'done_when', dedupe_hash: fullHash,
    });
    expect(h.cells(h.submit('[issue] remote-server: Other'))).toMatchObject({ status: 'NEEDS_INFO', missing_fields: 'problem,done_when' });
    expect(h.issues()).toBe(0);
  });

  it('marks a resubmission with the same normalized title and repo DUPLICATE', () => {
    const h = setup();
    h.submit(row.note);
    expect(h.cells(h.submit(row.note)).status).toBe('DUPLICATE');
    const reworded = '[issue] remote-server:   CHECK  queue\nProblem: Different text.\nDone when: Different check.';
    const cells = h.cells(h.submit(reworded));
    expect(cells.status).toBe('DUPLICATE');
    expect(cells.dedupe_hash).toBe(fullHash);
    expect(h.cells(h.submit(row.note.replace('Check queue', 'Another queue'))).status).toBe('NEW');
  });

  it('keeps issue creation on the existing dedup key', () => {
    const h = setup();
    h.submit(row.note);
    h.submit(row.note);
    expect(h.issues()).toBe(1);
    h.submit('[issue] remote-server: CHECK queue\nProblem: Different text.\nDone when: Different check.');
    expect(h.issues()).toBe(2);
  });

  it('does not treat a complete resubmission of an incomplete row as a duplicate', () => {
    const h = setup();
    expect(h.cells(h.submit('[issue] remote-server: Check queue')).status).toBe('NEEDS_INFO');
    expect(h.cells(h.submit('[issue] remote-server: Check queue')).status).toBe('NEEDS_INFO');
    expect(h.cells(h.submit(row.note)).status).toBe('NEW');
  });

  it('does not mark a title DUPLICATE when no issue was created (daily cap)', () => {
    const h = setup();
    h.stored.set('intake-day', JSON.stringify({ day: new Date().toISOString().slice(0, 10), count: 5, notified: true }));
    expect(h.cells(h.submit(row.note)).status).toBe('NEW');
    expect(h.cells(h.submit(row.note)).status).toBe('NEW');
    expect(h.issues()).toBe(0);
  });

  it('never writes READY or DISPATCHED', () => {
    const h = setup();
    const notes = [row.note, row.note, '[issue] remote-server: A', '[issue] remote-server: B\nProblem: p\nDone when: d'];
    const statuses = notes.map(note => h.cells(h.submit(note)).status);
    expect(new Set(statuses)).toEqual(new Set(['NEW', 'DUPLICATE', 'NEEDS_INFO']));
  });

  it('creates missing headers to the right of the form columns, once', () => {
    const h = setup();
    h.submit(row.note);
    expect(h.grid[0]).toEqual([...HEADERS, 'intake_id', 'dedupe_hash', 'missing_fields', 'status']);
    const headerWrites = h.writes.filter(write => write.row === 1);
    expect(headerWrites).toHaveLength(1);
    expect(headerWrites[0]).toMatchObject({ col: 6, values: [['intake_id', 'dedupe_hash', 'missing_fields', 'status']] });
    h.submit(row.note);
    expect(h.writes.filter(write => write.row === 1)).toHaveLength(1);
  });

  it('finds existing columns by header name even when form columns shift', () => {
    const h = setup(['Timestamp', 'status', 'Agent / Source', 'dedupe_hash', 'Item / Note', 'Status', 'Link', 'notes', 'intake_id']);
    const rowNumber = h.submit(row.note);
    expect(h.grid[0]).toHaveLength(10);
    expect(h.grid[0][9]).toBe('missing_fields');
    expect(h.cells(rowNumber)).toMatchObject({ intake_id: 'ledger-intake-' + fullHash.slice(0, 24), dedupe_hash: fullHash, status: 'NEW' });
    expect(h.cells(rowNumber)).toMatchObject({ 'Item / Note': row.note, 'Agent / Source': row.source, Status: 'Act', notes: '', status: 'NEW' });
  });

  it('writes the four values in one batched write per row and leaves other cells alone', () => {
    const h = setup([...HEADERS, 'intake_id', 'dedupe_hash', 'missing_fields', 'status']);
    const rowNumber = h.submit(row.note);
    expect(h.writes.filter(write => write.row === rowNumber)).toHaveLength(1);
    expect(h.writes.filter(write => write.row === rowNumber)[0]).toMatchObject({ col: 6, values: [[expect.any(String), fullHash, '', 'NEW']] });
    h.submit(row.note);
    expect(h.writes.filter(write => write.row === rowNumber + 1)).toHaveLength(1);
    expect(h.cells(rowNumber)['Item / Note']).toBe(row.note);
  });

  it('ignores ineligible submissions without touching the sheet', () => {
    const h = setup();
    h.submit(row.note, { Status: 'Done' });
    h.submit('[issue] other-repo: Nope');
    expect(h.writes).toEqual([]);
    expect(h.grid[0]).toEqual(HEADERS);
  });
});
