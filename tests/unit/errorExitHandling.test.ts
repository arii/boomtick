import { describe, expect, it, vi } from 'vitest';

describe('Error Exit Handling', () => {
  it('exits with code 1 when an unhandled exception occurs', async () => {
    const exitSpy = vi.spyOn(process, 'exit').mockImplementation((() => {}) as never);
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const runner = async () => {
      try {
        throw new Error('API Rate Limit Exceeded');
      } catch (err) {
        console.error('Fatal execution error:', err);
        process.exit(1);
      }
    };

    await runner();

    expect(exitSpy).toHaveBeenCalledWith(1);
    expect(consoleSpy).toHaveBeenCalledWith('Fatal execution error:', expect.any(Error));

    exitSpy.mockRestore();
    consoleSpy.mockRestore();
  });
});
