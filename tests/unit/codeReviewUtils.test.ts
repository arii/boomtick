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
  withRetry
} from '../../lib/codeReviewUtils';
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

  describe('parseCodeReviewStateDetailed and parseCodeReviewState', () => {
    it('parses valid JSON findings including new fields', () => {
      const json = JSON.stringify({
        findings: [{
          id: '1',
          file: 'test.ts',
          issue: 'test',
          status: 'open',
          confidence: 'high',
          counterexample: 'Example'
        }]
      });
      const feedback = `Some text\n<findings>\n${json}\n</findings>\nMore text`;
      const result = parseCodeReviewStateDetailed(feedback);
      expect(result.state?.findings.length).toBe(1);
      expect(result.state?.findings[0].id).toBe('1');
      expect(result.state?.findings[0].confidence).toBe('high');
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
      expect(result.diffText).toContain('...[TRUNCATED TO FIT TOKEN LIMIT]');
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
        const result = budgetInputContext(systemPrompt, { diffContext: diffText, externalContext: externalText }, 16000);

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
