import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
vi.mock('../../lib/visualReviewConstants', () => ({ ARTIFACTS_DIR: 'artifacts' }));
import { runReviewScript } from '../../scripts/utils/reviewScriptRunner';

let cwd: string;
let root: string;
let apiKey: string | undefined;
let argv: string[];
beforeEach(() => {
  cwd = process.cwd();
  root = fs.mkdtempSync(path.join(os.tmpdir(), 'review-script-'));
  process.chdir(root);
  apiKey = process.env.GEMINI_API_KEY;
  delete process.env.GEMINI_API_KEY;
  argv = process.argv;
  process.argv = ['node', 'runner.cjs', 'gemini'];
});
afterEach(() => {
  process.chdir(cwd);
  fs.rmSync(root, { recursive: true, force: true });
  process.argv = argv;
  if (apiKey === undefined) delete process.env.GEMINI_API_KEY;
  else process.env.GEMINI_API_KEY = apiKey;
});
const client = { reportFileName: 'gemini-code-review.md', reportTitle: 'Review fixture' };
describe('review script credential precondition', () => {
  it('writes an incomplete verdict and rejects before orchestration if the key is missing', async () => {
    const orchestrate = vi.fn();
    await expect(runReviewScript({ geminiClient: client, orchestrateGemini: orchestrate, scriptName: 'code review' }))
      .rejects.toThrow('GEMINI_API_KEY not set');
    expect(orchestrate).not.toHaveBeenCalled();
    const result = JSON.parse(fs.readFileSync('artifacts/gemini-code-review-verdict.json', 'utf8'));
    expect(result).toMatchObject({ passed: false, skipReason: 'MISSING_API_KEY', llmVerdict: 'warn' });
    expect(fs.readFileSync('artifacts/gemini-code-review.md', 'utf8')).toContain('incomplete, not approved');
  });
  it('does not replace the failing credential precondition with success when artifact writing fails', async () => {
    fs.writeFileSync('artifacts', 'a file prevents creating the artifacts directory');
    const orchestrate = vi.fn();
    await expect(runReviewScript({ geminiClient: client, orchestrateGemini: orchestrate, scriptName: 'code review' }))
      .rejects.toThrow('GEMINI_API_KEY not set');
    expect(orchestrate).not.toHaveBeenCalled();
  });
  it('uses the actual orchestration result when credentials are provided', async () => {
    process.env.GEMINI_API_KEY = 'offline fixture, no network';
    const orchestrate = vi.fn().mockRejectedValue(new Error('review unavailable'));
    await expect(runReviewScript({ geminiClient: client, orchestrateGemini: orchestrate, scriptName: 'code review' }))
      .rejects.toThrow('review unavailable');
    expect(orchestrate).toHaveBeenCalledOnce();
    expect(fs.existsSync('artifacts')).toBe(false);
  });
});
