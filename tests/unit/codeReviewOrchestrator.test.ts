import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { reconcileVerdict } from '../../lib/codeReviewOrchestrator';

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
