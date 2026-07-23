import { describe, it, expect } from 'vitest';
import fs from 'node:fs';

describe('Submodule Dockerfile Validation', () => {
  it('should pin Node 24.16.0 and pnpm 10.28.2 in boomtick-pkg/Dockerfile', () => {
    const dockerfileContent = fs.readFileSync('boomtick-pkg/Dockerfile', 'utf8');

    expect(dockerfileContent).toContain('NODE_VERSION=24.16.0');
    expect(dockerfileContent).toContain('PNPM_VERSION=10.28.2');
    expect(dockerfileContent).toContain('td-cli');
  });
});
