import { execSync } from 'child_process';
import { describe, expect, it } from 'vitest';

describe('Standalone td-cli Execution', () => {
  it('should execute doctor command cleanly without submodule paths', () => {
    const output = execSync('td-cli doctor', { encoding: 'utf-8' });
    expect(output).toContain('Runtime Consistency Check');
    expect(output).not.toContain('boomtick-pkg');
  });

  it('should return valid JSON schema for gh commands', () => {
    const output = execSync('td-cli config view --json', { encoding: 'utf-8' });
    const parsed = JSON.parse(output);
    expect(parsed).toHaveProperty('packageName');
  });
});
