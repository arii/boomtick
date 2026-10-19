import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';
import { sendJulesImpactReport } from '../../lib/julesReviewClient';

describe('sendJulesImpactReport', () => {
  const originalEnv = { ...process.env };
  const tmpArtifacts = path.join(process.cwd(), 'artifacts');

  beforeEach(() => {
    process.env = { ...originalEnv };
    delete process.env.JULES_API_KEY;
    if (fs.existsSync(tmpArtifacts)) {
      fs.rmSync(tmpArtifacts, { recursive: true, force: true });
    }
  });

  afterEach(() => {
    process.env = originalEnv;
    if (fs.existsSync(tmpArtifacts)) {
      fs.rmSync(tmpArtifacts, { recursive: true, force: true });
    }
  });

  it('exits early if taskId is empty', async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);

    await sendJulesImpactReport('');
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('exits early if JULES_API_KEY is not set', async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);

    await sendJulesImpactReport('12345');
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('sends message to Jules API when actionable reviews exist', async () => {
    process.env.JULES_API_KEY = 'test-jules-key';

    fs.mkdirSync(tmpArtifacts, { recursive: true });
    fs.writeFileSync(path.join(tmpArtifacts, 'deployment-review.md'), '## Impact Summary\nHigh severity changes.');
    fs.writeFileSync(
      path.join(tmpArtifacts, 'gemini-code-review-verdict.json'),
      JSON.stringify({ llmVerdict: 'fail', highCount: 2, passed: false })
    );

    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      text: async () => 'OK',
    });
    vi.stubGlobal('fetch', fetchSpy);

    await sendJulesImpactReport('12345');

    expect(fetchSpy).toHaveBeenCalledWith(
      'https://jules.googleapis.com/v1alpha/sessions/12345:sendMessage',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'x-goog-api-key': 'test-jules-key',
        }),
      })
    );
  });
});
