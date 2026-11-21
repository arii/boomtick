import { beforeEach, describe, expect, it, vi } from 'vitest';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import type { CodeReviewResult } from '../../lib/codeReviewTypes';

const mocks = vi.hoisted(() => {
  const exec = vi.fn();
  Object.defineProperty(exec, Symbol.for('nodejs.util.promisify.custom'), { value: exec, configurable: true });
  return { exec, spawn: vi.fn(), write: vi.fn(), post: vi.fn(), previous: vi.fn(), quota: vi.fn() };
});
vi.mock('child_process', () => ({ execFile: mocks.exec, spawn: mocks.spawn }));
vi.mock('fs', () => ({
  existsSync: () => true,
  mkdirSync: vi.fn(),
  promises: { readFile: async () => 'export const value = 2;', writeFile: mocks.write },
  appendFileSync: vi.fn(),
}));
vi.mock('../../lib/visualReviewUtils', () => ({
  countExistingReviews: async () => 0,
  getPreviousReviewState: mocks.previous,
  postPRComment: mocks.post,
}));
vi.mock('../../lib/projectConfig', () => ({ loadProjectConfig: () => ({ max_diff_chars: 200000 }) }));
vi.mock('../../lib/aiLogger', () => ({ logReviewExecution: vi.fn() }));
vi.mock('../../lib/sharedUtils', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/sharedUtils')>();
  return { ...actual, checkReviewQuota: mocks.quota };
});
import { orchestrateCodeReview } from '../../lib/codeReviewOrchestrator';
import { withRetry } from '../../lib/codeReviewUtils';

const client = {
  botName: 'offline-test', reportTitle: 'Offline review', botTagline: 'fixture',
  reportFileName: 'offline-test.md', invokeReview: vi.fn(),
};
const clean = (): CodeReviewResult => ({
  feedback: 'Reviewed the diff.', findings: [], state: { findings: [] },
  tokens: 10, cost: 0, modelName: 'offline-fixture', llmVerdict: 'pass',
});
function verdict() {
  const call = mocks.write.mock.calls.find(([path]) => String(path).endsWith('-verdict.json'));
  expect(call).toBeDefined();
  return JSON.parse(call![1]);
}
function contextProcess(error?: Error) {
  const child = Object.assign(new EventEmitter(), {
    stdout: new PassThrough(), stderr: new PassThrough(), stdin: new PassThrough(),
  });
  queueMicrotask(() => {
    if (error) child.emit('error', error);
    else { child.stdout.emit('data', '[]'); child.emit('close', 0); }
  });
  return child;
}

beforeEach(() => {
  vi.clearAllMocks();
  delete process.env.GITHUB_TOKEN;
  mocks.previous.mockResolvedValue(undefined);
  mocks.quota.mockResolvedValue(false);
  mocks.write.mockResolvedValue(undefined);
  mocks.exec.mockImplementation(async (_cmd, args) => ({ stdout:
    args.includes('rev-parse') ? 'abc' : args.includes('--name-only') ? 'src/file.ts' :
      args.includes('diff') ? 'diff --git a/src/file.ts b/src/file.ts\n@@ -1 +1 @@\n-export const value = 1;\n+export const value = 2;\n' : '',
  }));
  mocks.spawn.mockImplementation(() => contextProcess());
  client.invokeReview.mockImplementation(async () => clean());
});

describe('code review completeness', () => {
  it('does not call the provider when td context is unavailable and writes a failing verdict', async () => {
    mocks.spawn.mockImplementation(() => contextProcess(new Error('spawn td ENOENT')));
    await expect(orchestrateCodeReview(client)).rejects.toThrow('Impact/semantic context unavailable');
    expect(client.invokeReview).not.toHaveBeenCalled();
    expect(verdict()).toMatchObject({ passed: false, skipReason: 'PREPARATION_FAILED', highCount: 0 });
    expect(mocks.write.mock.calls.some(([, text]) => String(text).includes('ENOENT'))).toBe(true);
  });

  it('fails closed on git errors rather than reporting no changes', async () => {
    mocks.exec.mockRejectedValue(new Error('git diff unavailable'));
    await expect(orchestrateCodeReview(client)).rejects.toThrow('git diff unavailable');
    expect(verdict().passed).toBe(false);
    expect(client.invokeReview).not.toHaveBeenCalled();
  });

  it.each(['429 monthly spending cap exceeded', '401 unauthorized', 'network unavailable'])(
    'retains failed task evidence and rejects: %s', async (message) => {
      client.invokeReview.mockRejectedValue(new Error(message));
      await expect(orchestrateCodeReview(client)).rejects.toThrow('Code review incomplete');
      const result = verdict();
      expect(result.passed).toBe(false);
      expect(result.state.cache).toEqual({});
      const report = mocks.write.mock.calls.find(([path]) => String(path).endsWith('.md'))![1];
      expect(report).toContain('INCOMPLETE, NOT APPROVED');
      expect(report).toContain(message);
      expect(report).toContain('SECURITY');
      expect(mocks.post).toHaveBeenCalledWith(expect.stringContaining(message), client.reportTitle, expect.anything(), 'warn');
    },
  );

  it('rejects a partial failure even when other specialists pass', async () => {
    client.invokeReview.mockImplementation(async (summary) => {
      if (summary.role === 'SECURITY') throw new Error('quota unavailable');
      return clean();
    });
    await expect(orchestrateCodeReview(client)).rejects.toThrow('Code review incomplete');
    expect(verdict().passed).toBe(false);
    expect(Object.keys(verdict().state.cache)).toHaveLength(3);
  });

  it('rejects truncated output after bounded retry and does not cache it', async () => {
    client.invokeReview.mockResolvedValue({ ...clean(), isTruncated: true });
    await expect(orchestrateCodeReview(client)).rejects.toThrow('TRUNCATED');
    expect(client.invokeReview).toHaveBeenCalledTimes(8);
    expect(verdict().passed).toBe(false);
    expect(verdict().state.cache).toEqual({});
  });

  it('rejects malformed output even when findings is an array', async () => {
    client.invokeReview.mockResolvedValue({ ...clean(), parseError: 'invalid_json' });
    await expect(orchestrateCodeReview(client)).rejects.toThrow('PARSE_ERROR');
    expect(verdict().passed).toBe(false);
    expect(verdict().state.cache).toEqual({});
  });

  it('keeps successful warnings reviewable rather than treating every warning as unavailable', async () => {
    client.invokeReview.mockResolvedValue({ ...clean(), llmVerdict: 'warn' });
    await expect(orchestrateCodeReview(client)).resolves.toBeUndefined();
    expect(verdict()).toMatchObject({ passed: true, llmVerdict: 'warn' });
    expect(Object.keys(verdict().state.cache)).toHaveLength(4);
  });

  it('throws on a substantive fail after preserving its report and verdict', async () => {
    client.invokeReview.mockResolvedValue({ ...clean(), llmVerdict: 'fail', state: { findings: [
      { id: '1', file: 'src/file.ts', issue: 'fixture', status: 'open', severity: 'HIGH', confidence: 'high' },
    ] } });
    await expect(orchestrateCodeReview(client)).rejects.toThrow('Code review returned FAIL');
    expect(verdict()).toMatchObject({ passed: false, llmVerdict: 'fail' });
  });

  it('preserves top-level Gemini findings when no nested state was supplied', async () => {
    const result = clean();
    delete result.state;
    result.llmVerdict = 'fail';
    result.findings = [{ id: 'top', file: 'src/file.ts', issue: 'actual parsed finding', status: 'open', severity: 'HIGH', confidence: 'high' }];
    client.invokeReview.mockResolvedValue(result);
    await expect(orchestrateCodeReview(client)).rejects.toThrow('Code review returned FAIL');
    expect(verdict().state.findings).toContainEqual(expect.objectContaining({ id: 'top', status: 'open' }));
  });

  it('does not resolve previous findings or reuse incomplete cache entries on failed review', async () => {
    await orchestrateCodeReview(client);
    const cache = verdict().state.cache;
    for (const result of Object.values(cache) as CodeReviewResult[]) result.skipReason = 'RATE_LIMIT';
    mocks.write.mockClear();
    client.invokeReview.mockClear();
    const previous = { id: 'previous', file: 'src/file.ts', issue: 'existing', snippet: 'not in diff', status: 'open' };
    mocks.previous.mockResolvedValue({ findings: [previous], cache });
    client.invokeReview.mockRejectedValue(new Error('429 quota'));
    await expect(orchestrateCodeReview(client)).rejects.toThrow('Code review incomplete');
    expect(client.invokeReview).toHaveBeenCalledTimes(4);
    expect(verdict().state.cache).toEqual({});
    expect(verdict().state.findings).toContainEqual(previous);
    expect(previous.status).toBe('open');
  });

  it('does not retry a permanent monthly cap but preserves bounded transient retries', async () => {
    const permanent = vi.fn().mockRejectedValue(new Error('429 monthly spending cap exceeded'));
    await expect(withRetry(permanent, { initialDelayMs: 0 })).rejects.toThrow('monthly spending cap');
    expect(permanent).toHaveBeenCalledTimes(1);
    const transient = vi.fn().mockRejectedValueOnce(new Error('429 temporary rate limit')).mockResolvedValue('ok');
    await expect(withRetry(transient, { initialDelayMs: 0, maxRetries: 1 })).resolves.toBe('ok');
    expect(transient).toHaveBeenCalledTimes(2);
  });

  it('does not turn review quota into a passing review', async () => {
    mocks.quota.mockResolvedValue(true);
    await expect(orchestrateCodeReview(client)).rejects.toThrow('review quota reached');
    expect(verdict()).toMatchObject({ passed: false, skipReason: 'REVIEW_QUOTA' });
    expect(client.invokeReview).not.toHaveBeenCalled();
  });
});
