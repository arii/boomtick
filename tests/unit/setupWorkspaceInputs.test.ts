// tests/unit/setupWorkspaceInputs.test.ts
import { describe, expect, it } from 'vitest';

interface WorkspaceSetupConfig {
  setupNode: boolean;
  setupPython: boolean;
  initSchema: boolean;
}

const resolveSetupConfig = (
  inputNode?: string,
  inputPython?: string,
  inputSchema?: string
): WorkspaceSetupConfig => {
  return {
    setupNode: inputNode !== 'false',
    setupPython: inputPython !== 'false',
    initSchema: inputSchema === 'true',
  };
};

describe('resolveSetupConfig', () => {
  it('enables all runtimes by default when inputs are omitted', () => {
    const config = resolveSetupConfig();
    expect(config.setupNode).toBe(true);
    expect(config.setupPython).toBe(true);
    expect(config.initSchema).toBe(false);
  });

  it('disables python runtime for TS-only jobs', () => {
    const config = resolveSetupConfig('true', 'false', 'false');
    expect(config.setupNode).toBe(true);
    expect(config.setupPython).toBe(false);
    expect(config.initSchema).toBe(false);
  });

  it('enables schema initialization when explicitly requested', () => {
    const config = resolveSetupConfig('true', 'true', 'true');
    expect(config.initSchema).toBe(true);
  });
});
