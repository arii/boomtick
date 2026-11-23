import { afterEach, describe, expect, it, vi } from 'vitest';

const finalizeVerdictGate = vi.fn();
const runReviewScript = vi.fn(async () => undefined);

vi.mock('../../lib/verdictGate', () => ({ finalizeVerdictGate }));
vi.mock('../../lib/githubAuth', () => ({ initializeGitHubAuth: vi.fn(async () => undefined) }));
vi.mock('../../lib/codeReviewOrchestrator', () => ({ orchestrateCodeReview: vi.fn() }));
vi.mock('../../scripts/utils/reviewScriptRunner', () => ({ runReviewScript, handleScriptError: vi.fn() }));

describe('impact-ai-code-review main wiring', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
    finalizeVerdictGate.mockClear();
    runReviewScript.mockClear();
  });

  async function runMain(): Promise<void> {
    await import('../../scripts/impact-ai-code-review');
    await vi.waitFor(() => expect(finalizeVerdictGate).toHaveBeenCalled());
  }

  it('calls finalizeVerdictGate after the review with the real report file name', async () => {
    vi.stubEnv('BOOMTICK_FAIL_ON_VERDICT', 'true');
    await runMain();
    expect(runReviewScript).toHaveBeenCalled();
    expect(finalizeVerdictGate).toHaveBeenCalledWith({ reportFileName: 'gemini-code-review.md', failOnVerdict: true });
    expect(runReviewScript.mock.invocationCallOrder[0]).toBeLessThan(finalizeVerdictGate.mock.invocationCallOrder[0]);
  });

  it('passes failOnVerdict=false unless the input is exactly true', async () => {
    vi.stubEnv('BOOMTICK_FAIL_ON_VERDICT', 'false');
    await runMain();
    expect(finalizeVerdictGate).toHaveBeenCalledWith(expect.objectContaining({ failOnVerdict: false }));
  });
});
