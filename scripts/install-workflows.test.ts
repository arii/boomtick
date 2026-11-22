import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.join(__dirname, '..');
const cliDir = path.join(repoRoot, 'cli');

// Run the td entry point straight from the repo's cli/ sources so the test
// does not depend on td being installed on PATH. Interpreter: repo .venv,
// then python3.
function pythonBin(): string {
  const venvPython = path.join(repoRoot, '.venv/bin/python');
  return fs.existsSync(venvPython) ? venvPython : 'python3';
}

describe('Workflow Installer Command', () => {
  const tmpDir = path.join(__dirname, 'tmp_target_repo');

  beforeEach(() => { fs.mkdirSync(tmpDir, { recursive: true }); });
  afterEach(() => { fs.rmSync(tmpDir, { recursive: true, force: true }); });

  it('should generate workflow templates in dry-run mode', () => {
    const output = execFileSync(
      pythonBin(),
      ['-c', 'import sys; from dev_tools.cli import main; sys.exit(main())', 'agent', 'install-workflows', '--target', tmpDir, '--dry-run'],
      { encoding: 'utf-8', env: { ...process.env, PYTHONPATH: cliDir } },
    );
    expect(output).toContain('DRY-RUN');
    expect(output).toContain('impact-analysis.yml');
  });
});
