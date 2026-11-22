import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { describe, expect, it } from 'vitest';

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
const row = { source: 'Gemini', note: '[issue] remote-server: Check queue', status: 'Act', link: '' };

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
