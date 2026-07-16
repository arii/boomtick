import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as fs from 'fs';

// Mock child_process.execFile BEFORE importing getCodeDiffSummary
vi.mock('child_process', async (importOriginal) => {
  const actual = await importOriginal<typeof import('child_process')>();
  return {
    ...actual,
    execFile: vi.fn(),
    spawn: vi.fn(() => ({
        stdout: { on: vi.fn() },
        stderr: { on: vi.fn() },
        on: vi.fn(),
        stdin: { write: vi.fn(), end: vi.fn() }
    })),
  };
});

// Import after mocks
import { getCodeDiffSummary } from '../../lib/codeReviewOrchestrator';
import * as child_process from 'child_process';

describe('getCodeDiffSummary directory handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('skips directories when gathering context', async () => {
    const mockExecFile = vi.mocked(child_process.execFile);
    
    mockExecFile.mockImplementation((cmd, args, options, cb): any => {
      const callback = typeof options === 'function' ? options : cb;
      const cmdArgs = Array.isArray(args) ? args : [];
      
      if (cmdArgs.includes('--name-only')) {
        callback(null, { stdout: 'boomtick-pkg\n' }, '');
      } else {
        callback(null, { stdout: 'some diff content' }, '');
      }
      return {} as any;
    });

    const dirPath = 'boomtick-pkg'; 
    const readFileSpy = vi.spyOn(fs.promises, 'readFile');

    await getCodeDiffSummary();
    
    const dirCalls = readFileSpy.mock.calls.filter(call => call[0] === dirPath);
    expect(dirCalls.length).toBe(0);
    
    readFileSpy.mockRestore();
  });
});
