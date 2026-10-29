import { describe, it, expect, vi } from 'vitest';
import {
  cleanupFeedback,
  extractFeedbackText,
  parseCodeReviewVerdict,
  parseCodeReviewStateDetailed,
  parseCodeReviewState,
  estimateMaxOutputTokens,
  budgetInputContext,
  buildReviewPayload,
  EXTERNAL_CONTEXT_TRUNCATED_MESSAGE,
  EXTERNAL_CONTEXT_MINIMUM_BUDGET,
  filterLowImpactFiles,
  filterUnifiedDiffByAST,
  filterUnifiedDiff,
  extractFilePathFromDiffHeader,
  truncateUnifiedDiff,
  withRetry
} from '../../lib/codeReviewUtils';
import { buildReviewComments, formatAsGitHubSuggestion } from '../../lib/visualReviewUtils';
import { buildSystemPrompt } from '../../lib/buildCodeReviewPrompt';


describe('codeReviewUtils', () => {
  describe('buildSystemPrompt', () => {
    it('includes goal section if provided', () => {
      const prompt = buildSystemPrompt({ diffContext: 'some diff', prGoal: 'Fix the bug' });
      expect(prompt).toContain('This PR\'s stated goal:');
      expect(prompt).toContain('Fix the bug');
    });

    it('does not include goal section if not provided', () => {
      const prompt = buildSystemPrompt({ diffContext: 'some diff' });
      expect(prompt).not.toContain('This PR\'s stated goal:');
    });

    it('includes previous findings if provided', () => {
      const prompt = buildSystemPrompt({
        diffContext: '',
        previousState: {
          findings: [
            { id: 'f-1', file: 'a.js', issue: 'Bad code', status: 'open' }
          ]
        }
      });
      expect(prompt).toContain('PREVIOUS REVIEW ROUND FINDINGS:');
      expect(prompt).toContain('- [f-1] a.js: Bad code (Status: open)');
    });

    it('includes all 3 mandatory sections', () => {
      const prompt = buildSystemPrompt({ diffContext: 'some diff' });




      expect(prompt).toContain('## 1. Philosophy');
      expect(prompt).toContain('## 2. Standards');
      expect(prompt).toContain('## 3. Checklist');
      expect(prompt).toContain('## 4. Severity');
      expect(prompt).toContain('## 5. Output');
    });
  });

  describe('cleanupFeedback', () => {
    it('strips findings and verdict tags', () => {
      const feedback = 'Review here.\n<findings>{"f":[]}</findings>\n[VERDICT: PASS]\nFooter.';
      expect(cleanupFeedback(feedback)).toBe('Review here.\n\nFooter.');
    });

    it('is case-insensitive and handles multiline findings', () => {
      const feedback = 'Start\n<FINDINGS>\nline1\nline2\n</FINDINGS>\n[verdict: FAIL]\nEnd';
      expect(cleanupFeedback(feedback)).toBe('Start\n\nEnd');
    });
  });

  describe('extractFeedbackText', () => {
    it('returns string content as is, stripping markdown code blocks if present', () => {
      expect(extractFeedbackText('Plain text')).toBe('Plain text');
      expect(extractFeedbackText('```json\n{ "test": 1 }\n```')).toBe('{ "test": 1 }');
    });

    it('joins text parts from an array, skipping thoughts', () => {
      const content = [
        { thought: 'Thinking...' },
        { text: 'Part 1 ' },
        { text: 'Part 2' }
      ];
      expect(extractFeedbackText(content)).toBe('Part 1 Part 2');
    });

    it('stringifies object content that is not an array', () => {
      const content = { unexpected: 'format' };
      expect(extractFeedbackText(content)).toBe(JSON.stringify(content));
    });

    it('stringifies array if no text content is found', () => {
      const content = [{ other: 'data' }];
      expect(extractFeedbackText(content)).toBe(JSON.stringify(content));
    });

    it('returns empty string for null/undefined content', () => {
      expect(extractFeedbackText(null)).toBe('');
      expect(extractFeedbackText(undefined)).toBe('');
    });
  });

  describe('parseCodeReviewVerdict', () => {
    it('parses PASS correctly', () => {
      expect(parseCodeReviewVerdict('Some feedback. [VERDICT: PASS]')).toBe('pass');
    });

    it('parses WARN correctly', () => {
      expect(parseCodeReviewVerdict('Some feedback. [VERDICT: WARN]')).toBe('warn');
    });

    it('parses FAIL correctly', () => {
      expect(parseCodeReviewVerdict('Some feedback. [VERDICT: FAIL]')).toBe('fail');
    });

    it('defaults to PASS if no valid verdict is found', () => {
      expect(parseCodeReviewVerdict('Some feedback without verdict.')).toBe('pass');
    });

    it('uses the last verdict if multiple are found', () => {
      expect(parseCodeReviewVerdict('Some feedback. [VERDICT: FAIL] But wait, [VERDICT: PASS]')).toBe('pass');
    });
  });

  describe('filterLowImpactFiles', () => {
    it('filters default lockfiles, minified files, maps, dist folders, and SVG/binary assets', () => {
      const files = [
        'src/index.ts',
        'pnpm-lock.yaml',
        'package-lock.json',
        'poetry.lock',
        'Cargo.lock',
        'Composer.lock',
        'Pipfile.lock',
        'flake.lock',
        'dist/bundle.js',
        'build/main.js',
        'coverage/lcov.info',
        'src/vendor.min.js',
        'src/styles.min.css',
        'src/app.js.map',
        'public/logo.svg',
        'src/assets/banner.png',
        'src/assets/photo.jpg',
        'src/fonts/inter.woff2',
        'src/binary.wasm',
        'src/archive.zip'
      ];
      const filtered = filterLowImpactFiles(files);
      expect(filtered).toEqual(['src/index.ts']);
    });
  });

  describe('extractFilePathFromDiffHeader', () => {
    it('extracts file path from git diff header', () => {
      expect(extractFilePathFromDiffHeader('diff --git a/src/app.ts b/src/app.ts')).toBe('src/app.ts');
      expect(extractFilePathFromDiffHeader('+++ b/lib/utils.ts')).toBe('lib/utils.ts');
      expect(extractFilePathFromDiffHeader('--- a/scripts/test.ts')).toBe('scripts/test.ts');
      expect(extractFilePathFromDiffHeader('no git header')).toBeUndefined();
    });
  });

  describe('filterUnifiedDiffByAST', () => {
    it('filters out lockfiles, build outputs, and SVG/binary assets from unified git diff', () => {
      const mixedDiff = [
        'diff --git a/pnpm-lock.yaml b/pnpm-lock.yaml',
        'index 1111..2222 100644',
        '--- a/pnpm-lock.yaml',
        '+++ b/pnpm-lock.yaml',
        '@@ -1,3 +1,3 @@',
        '- lockfile content old',
        '+ lockfile content new',
        'diff --git a/src/businessLogic.ts b/src/businessLogic.ts',
        'index 3333..4444 100644',
        '--- a/src/businessLogic.ts',
        '+++ b/src/businessLogic.ts',
        '@@ -10,3 +10,4 @@',
        ' export interface UserContract {',
        '-  id: string;',
        '+  id: string;',
        '+  email: string;',
        ' }',
        'diff --git a/public/logo.svg b/public/logo.svg',
        'index 5555..6666 100644',
        '--- a/public/logo.svg',
        '+++ b/public/logo.svg',
        '@@ -1,1 +1,1 @@',
        '-<svg><path d="M0 0"/></svg>',
        '+<svg><path d="M0 1"/></svg>',
        'diff --git a/dist/bundle.js b/dist/bundle.js',
        'index 7777..8888 100644',
        '--- a/dist/bundle.js',
        '+++ b/dist/bundle.js',
        '@@ -1,1 +1,1 @@',
        '-var a=1;',
        '+var a=2;'
      ].join('\n');

      const filtered = filterUnifiedDiffByAST(mixedDiff);

      expect(filtered).toContain('diff --git a/src/businessLogic.ts b/src/businessLogic.ts');
      expect(filtered).toContain('UserContract');
      expect(filtered).not.toContain('pnpm-lock.yaml');
      expect(filtered).not.toContain('public/logo.svg');
      expect(filtered).not.toContain('dist/bundle.js');
    });

    it('filters out binary file diffs and asset blobs', () => {
      const binaryDiff = [
        'diff --git a/assets/image.png b/assets/image.png',
        'Binary files a/assets/image.png and b/assets/image.png differ',
        'diff --git a/src/contract.ts b/src/contract.ts',
        '--- a/src/contract.ts',
        '+++ b/src/contract.ts',
        '@@ -1,2 +1,3 @@',
        '+export type ApiContract = { status: number };'
      ].join('\n');

      const filtered = filterUnifiedDiff(binaryDiff);

      expect(filtered).toContain('diff --git a/src/contract.ts b/src/contract.ts');
      expect(filtered).not.toContain('assets/image.png');
      expect(filtered).not.toContain('Binary files');
    });

    it('returns empty string if all diff chunks are low-impact or excluded', () => {
      const lockfileDiff = [
        'diff --git a/package-lock.json b/package-lock.json',
        '--- a/package-lock.json',
        '+++ b/package-lock.json',
        '@@ -1,2 +1,2 @@',
        '-{"name": "a"}',
        '+{"name": "b"}'
      ].join('\n');

      expect(filterUnifiedDiffByAST(lockfileDiff)).toBe('');
    });
  });

  describe('truncateUnifiedDiff', () => {
    it('preserves git headers and hunk headers while truncating inner lines', () => {
      const diff = [
        'diff --git a/src/index.ts b/src/index.ts',
        '--- a/src/index.ts',
        '+++ b/src/index.ts',
        '@@ -1,5 +1,5 @@',
        ' line 1',
        ' line 2',
        ' line 3',
        ' line 4'
      ].join('\n');

      const truncated = truncateUnifiedDiff(diff, 100);
      expect(truncated).toContain('diff --git');
      expect(truncated).toContain('@@ -1,5 +1,5 @@');
      expect(truncated).toContain('...[DIFF TRUNCATED TO FIT TOKEN BUDGET]');
    });

    it('truncates diff at AST declaration boundaries when exceeding character budget', () => {
      const diff = [
        'diff --git a/src/service.ts b/src/service.ts',
        '--- a/src/service.ts',
        '+++ b/src/service.ts',
        '@@ -1,20 +1,20 @@',
        '+ export function calculateTotal(items: number[]): number {',
        '+   return items.reduce((a, b) => a + b, 0);',
        '+ }',
        '+ export class UserService {',
        '+   async getUser(id: string) { return { id }; }',
        '+ }'
      ].join('\n');

      // Set maxChars tight enough to trigger truncation after headers and first AST export
      const truncated = truncateUnifiedDiff(diff, 180);

      expect(truncated).toContain('diff --git a/src/service.ts');
      expect(truncated).toContain('...[DIFF TRUNCATED TO FIT TOKEN BUDGET]');
      expect(truncated).not.toContain('async getUser(id: string)');
    });
  });

  describe('buildReviewComments and GitHub suggestion formatting', () => {
    it('formats raw code into GitHub suggestion blocks', () => {
      expect(formatAsGitHubSuggestion('const x = 2;')).toBe('```suggestion\nconst x = 2;\n```');
      expect(formatAsGitHubSuggestion('```typescript\nconst x = 2;\n```')).toBe('```suggestion\nconst x = 2;\n```');
      expect(formatAsGitHubSuggestion('```suggestion\nconst x = 2;\n```')).toBe('```suggestion\nconst x = 2;\n```');
    });

    it('generates GitHub-compatible suggestion fences in inline review comments', () => {
      const state = {
        findings: [
          {
            id: 'f-1',
            file: 'src/app.ts',
            line: 15,
            status: 'open',
            severity: 'HIGH',
            issue: 'Incorrect user assignment',
            suggestion: 'const user = fetchUser(id);'
          },
          {
            id: 'f-2',
            file: 'src/config.ts',
            line: 5,
            status: 'open',
            severity: 'MEDIUM',
            issue: 'Use const over let',
            fixSummary: '```typescript\nconst port = 8080;\n```'
          }
        ]
      };

      const comments = buildReviewComments(state);
      expect(comments.length).toBe(2);

      expect(comments[0].path).toBe('src/app.ts');
      expect(comments[0].line).toBe(15);
      expect(comments[0].body).toContain('```suggestion\nconst user = fetchUser(id);\n```');

      expect(comments[1].path).toBe('src/config.ts');
      expect(comments[1].line).toBe(5);
      expect(comments[1].body).toContain('```suggestion\nconst port = 8080;\n```');
    });
  });

  describe('parseCodeReviewStateDetailed and parseCodeReviewState', () => {
    it('parses valid JSON findings including new fields', () => {
      const json = JSON.stringify({
        findings: [{
          id: '1',
          file: 'test.ts',
          issue: 'test',
          status: 'open',
          confidence: 'high',
          startLine: 10,
          endLine: 12,
          suggestion: '```suggestion\nconst a = 1;\n```',
          counterexample: 'Example'
        }]
      });
      const feedback = `Some text\n<findings>\n${json}\n</findings>\nMore text`;
      const result = parseCodeReviewStateDetailed(feedback);
      expect(result.state?.findings.length).toBe(1);
      expect(result.state?.findings[0].id).toBe('1');
      expect(result.state?.findings[0].confidence).toBe('high');
      expect(result.state?.findings[0].startLine).toBe(10);
      expect(result.state?.findings[0].endLine).toBe(12);
      expect(result.state?.findings[0].suggestion).toContain('```suggestion');
      expect(result.state?.findings[0].counterexample).toBe('Example');
      expect(result.parseError).toBeUndefined();

      expect(parseCodeReviewState(feedback)?.findings.length).toBe(1);
    });

    it('normalizes invalid confidence levels to medium', () => {
        const json = JSON.stringify({
          findings: [{
            id: '1',
            file: 'test.ts',
            issue: 'test',
            status: 'open',
            confidence: 'INVALID'
          }]
        });
        const feedback = `<findings>${json}</findings>`;
        const result = parseCodeReviewStateDetailed(feedback);
        expect(result.state?.findings[0].confidence).toBe('medium');
        expect(result.parseError).toBeUndefined();
    });

    it('handles missing closing tag by still returning parsed state but with error', () => {
      const feedback = `Some text\n<findings>\n{"findings": []}`;
      const result = parseCodeReviewStateDetailed(feedback);
      expect(result.state).toBeDefined();
      expect(result.state?.findings).toEqual([]);
      expect(result.parseError).toBe('missing_closing_tag');
    });

    it('handles invalid JSON', () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      const feedback = `Some text\n<findings>\nbad json\n</findings>`;
      const result = parseCodeReviewStateDetailed(feedback);
      expect(result.state).toBeUndefined();
      expect(result.parseError).toBe('invalid_json');
      consoleSpy.mockRestore();
    });

    it('safely parses JSON containing unescaped backslashes in regex/snippets', () => {
      const badEscapedJson = '{"findings": [{"id": "1", "file": "utils.ts", "issue": "test", "status": "open", "snippet": "replace(/\\s*/)"}]}';
      const feedback = `<findings>${badEscapedJson}</findings>`;
      const result = parseCodeReviewStateDetailed(feedback);
      expect(result.state).toBeDefined();
      expect(result.state?.findings[0].snippet).toBe('replace(/\\s*/)');
      expect(result.parseError).toBeUndefined();
    });

    it('handles no findings tags', () => {
      const result = parseCodeReviewStateDetailed('No findings tag here');
      expect(result.state).toBeUndefined();
      expect(result.parseError).toBeUndefined();
    });
  });

  describe('estimateMaxOutputTokens', () => {
    it('returns base budget for empty diff and no findings', () => {
      // estimatedOutput = 0
      // thinkingBudget = 2048
      // outputPadding = 256
      // priorFindingsBudget = 0
      expect(estimateMaxOutputTokens({ diffContext: '' })).toBe(2304);
    });

    it('scales up based on prior findings count', () => {
      const withFindings = estimateMaxOutputTokens({
        diffContext: '',
        previousState: {
          findings: Array.from({ length: 5 }, (_, i) => ({ id: `f-${i}`, file: 'f', issue: 'i', status: 'open' }))
        }
      });
      // 2304 + (5 * 200) = 3304
      expect(withFindings).toBe(3304);
    });

    it('adds tokens for large diffs capped at 2000', () => {
      // 4000 tokens * 4 chars = 16000 chars -> diffTokens = 4000
      // 4000 * 0.4 = 1600 estimatedOutput
      // 1600 + 2048 + 256 = 3904
      const largeDiff = 'a'.repeat(16001);
      expect(estimateMaxOutputTokens({ diffContext: largeDiff })).toBe(3905);
    });

    it('caps at 8192', () => {
      const hugeDiff = 'a'.repeat(16001);
      const manyFindings = estimateMaxOutputTokens({
        diffContext: hugeDiff,
        previousState: {
          findings: Array.from({ length: 40 }, (_, i) => ({ id: `f-${i}`, file: 'f', issue: 'i', status: 'open' }))
        }
      });
      // estimatedOutput = 1600 (capped at 2000)
      // priorFindingsBudget = 40 * 200 = 8000
      // total > 8192
      expect(manyFindings).toBe(8192);
    });
  });

  describe('budgetInputContext', () => {
    const defaultMaxChars = 24000;

    it('returns untouched strings if within budget', () => {
      const systemPrompt = 'Prompt';
      const diffText = 'Diff';
      const externalText = 'External';
      const result = budgetInputContext(systemPrompt, { diffContext: diffText, externalContext: externalText }, defaultMaxChars);

      expect(result.diffText).toBe(diffText);
      expect(result.externalText).toBe(externalText);
    });

    it('truncates diff string if exceeding 16000 chars when budgeting', () => {
      const systemPrompt = 'Prompt';
      const diffText = 'a'.repeat(20000);
      const result = budgetInputContext(systemPrompt, { diffContext: diffText }, 16000);

      expect(result.diffText.length).toBeLessThan(16000 + 100);
      expect(result.diffText).toContain('...[DIFF TRUNCATED TO FIT TOKEN BUDGET]');
    });

    it('allocates remaining budget to external text', () => {
      const systemPrompt = 'Prompt';
      const diffText = 'a'.repeat(16000); // Uses 16k max for diff
      const externalText = 'b'.repeat(10000); // Would exceed 24k total
      const result = budgetInputContext(systemPrompt, { diffContext: diffText, externalContext: externalText }, defaultMaxChars);

      expect(result.externalText).toContain('...[TRUNCATED TO FIT TOKEN LIMIT]');
    });

    it(`hard truncates external context if budget remaining is extremely small (<= ${EXTERNAL_CONTEXT_MINIMUM_BUDGET})`, () => {
        const systemPrompt = 'Prompt';
        const diffText = 'a'.repeat(16000);
        const externalText = 'External context that should be dropped';
        // maxInputChars = systemPrompt.length + 16000 + 10 -> remaining for external = 10 (which is <= 200)
        const maxInputChars = systemPrompt.length + 16000 + 10;
        const result = budgetInputContext(systemPrompt, { diffContext: diffText, externalContext: externalText }, maxInputChars);

        expect(result.externalText).toBe(EXTERNAL_CONTEXT_TRUNCATED_MESSAGE);
    });
  });

  describe('buildReviewPayload', () => {
    it('applies prefixes to payload texts', () => {
      const payload = buildReviewPayload('Prompt', 'Diff content', 'External content');
      expect(payload[0]).toEqual({ role: 'system', content: 'Prompt' });
      expect(payload[1]).toEqual({ role: 'user', content: 'DIFF:\n\nDiff content' });
      expect(payload[2]).toEqual({ role: 'system', content: 'EXTERNAL CONTEXT (Types/Interfaces/Constants referenced in the diff):\n\nExternal content' });
    });

    it('applies custom prefixes to payload texts', () => {
      const payload = buildReviewPayload('Prompt', 'Diff content', 'External content', {
        diffPrefix: 'CustomDiff:\n',
        externalPrefix: 'CustomExt:\n',
      });
      expect(payload[1]).toEqual({ role: 'user', content: 'CustomDiff:\nDiff content' });
      expect(payload[2]).toEqual({ role: 'system', content: 'CustomExt:\nExternal content' });
    });

    it('does not apply prefix if external text is fully truncated', () => {
      const payload = buildReviewPayload('Prompt', 'Diff content', EXTERNAL_CONTEXT_TRUNCATED_MESSAGE);
      expect(payload[2]).toEqual({ role: 'system', content: EXTERNAL_CONTEXT_TRUNCATED_MESSAGE });
    });
  });

  describe('withRetry', () => {
    it('should return result immediately if first call succeeds', async () => {
      const fn = vi.fn().mockResolvedValue('success');
      const result = await withRetry(fn, { maxRetries: 3, initialDelayMs: 1 });
      expect(result).toBe('success');
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it('should retry on transient error (429) and succeed eventually', async () => {
      let count = 0;
      const fn = vi.fn().mockImplementation(async () => {
        count++;
        if (count < 3) {
          throw new Error('API error: 429 Rate Limit Exceeded');
        }
        return 'success';
      });

      const result = await withRetry(fn, { maxRetries: 3, initialDelayMs: 1, jitter: false });
      expect(result).toBe('success');
      expect(fn).toHaveBeenCalledTimes(3);
    });

    it('should fail immediately on non-transient errors (like 401)', async () => {
      const fn = vi.fn().mockRejectedValue(new Error('API error: 401 Unauthorized'));
      await expect(withRetry(fn, { maxRetries: 3, initialDelayMs: 1 })).rejects.toThrow('API error: 401');
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it('should propagate last error if all retries are exhausted', async () => {
      const fn = vi.fn().mockRejectedValue(new Error('API error: 502 Bad Gateway'));
      await expect(withRetry(fn, { maxRetries: 2, initialDelayMs: 1, jitter: false })).rejects.toThrow('API error: 502');
      expect(fn).toHaveBeenCalledTimes(3); // 1 initial + 2 retries
    });
  });
});
