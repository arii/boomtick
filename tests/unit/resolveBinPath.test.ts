import { describe, expect, it } from 'vitest';
import * as path from 'path';

const resolveBinPath = (workspaceRoot: string): string => {
  return path.join(workspaceRoot, 'node_modules', '.bin');
};

const buildExecEnv = (workspaceRoot: string, currentPath: string): Record<string, string> => {
  const binPath = resolveBinPath(workspaceRoot);
  return {
    PATH: `${binPath}:${currentPath}`
  };
};

describe('resolveBinPath', () => {
  it('constructs correct bin path for given workspace root', () => {
    const root = '/custom/workspace/path';
    expect(resolveBinPath(root)).toBe('/custom/workspace/path/node_modules/.bin');
  });

  it('prepends resolved bin path to PATH environment variable', () => {
    const root = '/app/runner';
    const env = buildExecEnv(root, '/usr/bin:/bin');
    expect(env.PATH).toBe('/app/runner/node_modules/.bin:/usr/bin:/bin');
  });
});
