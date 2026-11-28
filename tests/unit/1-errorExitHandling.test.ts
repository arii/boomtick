import { describe, expect, it, vi } from 'vitest';

describe('handleScriptError', () => {
  it('exits 1 so hard errors still fail the step regardless of fail-on-verdict', async () => {
    const { handleScriptError } = await import('../../scripts/utils/reviewScriptRunner');
    const exitSpy = vi.spyOn(process, 'exit').mockImplementation((() => {}) as never);
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    handleScriptError(new Error('boom'), 'code review');
    expect(exitSpy).toHaveBeenCalledWith(1);
    exitSpy.mockRestore();
    errSpy.mockRestore();
  });
});
