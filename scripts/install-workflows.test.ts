import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

describe('Workflow Installer Command', () => {
  const tmpDir = path.join(__dirname, 'tmp_target_repo');

  beforeEach(() => { fs.mkdirSync(tmpDir, { recursive: true }); });
  afterEach(() => { fs.rmSync(tmpDir, { recursive: true, force: true }); });

  it('should generate workflow templates in dry-run mode', () => {
    const output = execSync(`td-cli agent install-workflows --target ${tmpDir} --dry-run`, { encoding: 'utf-8' });
    expect(output).toContain('DRY-RUN');
    expect(output).toContain('impact-analysis.yml');
  });
});
