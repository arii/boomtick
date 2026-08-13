import { describe, expect, it } from 'vitest';
import * as path from 'path';

// Simulates the path resolution logic of resolve-cli.sh
const resolveBinPath = (workspaceRoot: string, pnpmBinProvider?: () => string | null): string => {
  try {
    const pnpmBin = pnpmBinProvider ? pnpmBinProvider() : null;
    if (pnpmBin) {
      return pnpmBin;
    }
  } catch {
    // Ignore and fall back
  }
  return path.join(workspaceRoot, 'node_modules', '.bin');
};

const buildExecEnv = (
  workspaceRoot: string,
  currentPath: string,
  pnpmBinProvider?: () => string | null
): Record<string, string> => {
  const binPath = resolveBinPath(workspaceRoot, pnpmBinProvider);
  return {
    PATH: `${binPath}:${currentPath}`
  };
};

describe('resolveBinPath', () => {
  it('uses pnpm bin result if available', () => {
    const root = '/custom/workspace/path';
    const mockPnpmBin = () => '/custom/workspace/path/.pnpm-bin';
    expect(resolveBinPath(root, mockPnpmBin)).toBe('/custom/workspace/path/.pnpm-bin');
  });

  it('falls back to node_modules/.bin if pnpm bin is not available or throws', () => {
    const root = '/custom/workspace/path';
    const mockPnpmBinFailure = () => { throw new Error('pnpm not found'); };
    expect(resolveBinPath(root, mockPnpmBinFailure)).toBe('/custom/workspace/path/node_modules/.bin');
    expect(resolveBinPath(root, () => null)).toBe('/custom/workspace/path/node_modules/.bin');
  });

  it('prepends resolved bin path to PATH environment variable', () => {
    const root = '/app/runner';
    const mockPnpmBin = () => '/app/runner/resolved-bin';
    const env = buildExecEnv(root, '/usr/bin:/bin', mockPnpmBin);
    expect(env.PATH).toBe('/app/runner/resolved-bin:/usr/bin:/bin');
  });
});
