import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { runDryRun } from '../../scripts/review-dry-run';

const fixture = (name: string) => path.join(__dirname, '../fixtures/review-dry-run', `${name}.json`);

describe('review dry-run', () => {
  it('pass fixture is green', async () => {
    const r = await runDryRun(fixture('pass'));
    expect(r.exitCode).toBe(0);
    expect(r.verdictJson?.llmVerdict).toBe('pass');
    expect(r.outputs).toContain('verdict=pass');
  });

  it('warn fixture is green', async () => {
    const r = await runDryRun(fixture('warn'));
    expect(r.exitCode).toBe(0);
    expect(r.verdictJson?.llmVerdict).toBe('warn');
  });

  it('fail fixture is red and names the blocking finding', async () => {
    const r = await runDryRun(fixture('fail'));
    expect(r.exitCode).toBe(1);
    expect(r.verdictJson?.llmVerdict).toBe('fail');
    expect(r.outputs).toContain('verdict=fail');
    expect(r.outputs).toContain('- [HIGH] src/app.ts:3 - User input is concatenated into a SQL query');
  });
});
