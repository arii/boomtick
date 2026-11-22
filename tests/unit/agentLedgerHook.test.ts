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
  it('uses the exact URL when present regardless of source or note', () => {
    const link = 'https://example.com/tasks/1?query=Two#anchor';
    expect(dedupKey({ ...row, link })).toBe(link);
    expect(dedupKey({ ...row, source: 'Instinct', note: '[issue] boomtick: New title', link })).toBe(link);
  });

  it('uses a short SHA-256 digest of source and the full note when the link is blank', () => {
    const note = '[issue] remote-server: Check queue\nRésumé';
    expect(dedupKey({ ...row, note })).toBe('cd9bf9d857de893e');
    expect(dedupKey({ ...row, note, status: 'Done' })).toBe(dedupKey({ ...row, note }));
    expect(dedupKey({ ...row, note, source: 'Instinct' })).not.toBe(dedupKey({ ...row, note }));
    expect(dedupKey(row)).not.toBe(dedupKey({ ...row, note }));
  });
});
