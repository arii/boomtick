import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

describe('Submodule Dockerfile Validation', () => {
  it('should pin Node 24.16.0 and pnpm 10.28.2 in Dockerfile', () => {
    // Dockerfile is at the root of the repository
    const dockerfileContent = fs.readFileSync(path.join(__dirname, '..', '..', 'Dockerfile'), 'utf8');

    expect(dockerfileContent).toContain('NODE_VERSION=24.16.0');
    expect(dockerfileContent).toContain('PNPM_VERSION=10.28.2');
    expect(dockerfileContent).toContain('ENTRYPOINT ["td-cli"]');
  });
});
