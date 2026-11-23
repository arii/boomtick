import { describe, expect, it } from 'vitest';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { deriveVerdictFromPrevState, writeGracefulExitVerdict, checkReviewQuota } from '../../lib/sharedUtils';

const open = (severity: string, status = 'open') => ({ id: 'F', file: 'a.ts', issue: 'x', status, severity });

describe('deriveVerdictFromPrevState', () => {
  it('is pass without state or open HIGH findings', () => {
    expect(deriveVerdictFromPrevState(undefined)).toBe('pass');
    expect(deriveVerdictFromPrevState(null)).toBe('pass');
    expect(deriveVerdictFromPrevState({ findings: [open('MEDIUM'), open('HIGH', 'resolved')] })).toBe('pass');
  });

  it('is fail when a HIGH or error finding is still open', () => {
    expect(deriveVerdictFromPrevState({ findings: [open('HIGH')] })).toBe('fail');
    expect(deriveVerdictFromPrevState({ findings: [open('error')] })).toBe('fail');
  });
});

describe('skip exits keep an earlier FAIL', () => {
  it('quota-met and filtered-only exits write fail when prevState has open HIGH findings', async () => {
    const prev = process.cwd();
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'verdict-'));
    process.chdir(dir);
    try {
      const artifacts = path.join(dir, 'artifacts');
      fs.mkdirSync(artifacts);
      const state = { findings: [open('HIGH')] };

      await writeGracefulExitVerdict('r.md', artifacts, state);
      expect(JSON.parse(fs.readFileSync(path.join(artifacts, 'r-verdict.json'), 'utf8')).llmVerdict).toBe('fail');

      await writeGracefulExitVerdict('r.md', artifacts, null);
      expect(JSON.parse(fs.readFileSync(path.join(artifacts, 'r-verdict.json'), 'utf8')).llmVerdict).toBe('pass');

      await checkReviewQuota(3, 3, 'bot', 'Title', path.join(artifacts, 'r.md'), 'r.md', artifacts, async () => state);
      expect(JSON.parse(fs.readFileSync(path.join(artifacts, 'r-verdict.json'), 'utf8')).llmVerdict).toBe('fail');
    } finally {
      process.chdir(prev);
    }
  });
});
