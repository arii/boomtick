import { execFile, type ExecException } from 'node:child_process';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SCRIPT = path.join(__dirname, 'verify-schemas.mjs');

function runScript(cwd: string): Promise<{ code: number | string; output: string }> {
  return new Promise((resolve) => {
    execFile(
      'node',
      [SCRIPT],
      { cwd, timeout: 60000 },
      (error: ExecException | null, stdout: string, stderr: string) => {
        resolve({ code: error?.code ?? 0, output: `${stdout}\n${stderr}` });
      },
    );
  });
}

describe('verify-schemas fail-closed toolchain (issue #1226)', () => {
  let scratch: string;

  beforeEach(() => {
    scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'verify-schemas-'));
  });

  afterEach(() => {
    fs.rmSync(scratch, { recursive: true, force: true });
  });

  it('exits non-zero naming the missing python binary when the venv is absent', async () => {
    const { code, output } = await runScript(scratch);
    expect(code).toBe(254);
    expect(output).toContain('Missing required toolchain binary: .venv/bin/python3');
    expect(output).toContain('setup-agent.sh');
  });

  it('never falls back to an ambient python3 on PATH', async () => {
    const { output } = await runScript(scratch);
    expect(output).not.toContain('Using Python: python3');
  });

  it('exits non-zero naming td when python is present but td is absent', async () => {
    fs.mkdirSync(path.join(scratch, '.venv', 'bin'), { recursive: true });
    fs.writeFileSync(path.join(scratch, '.venv', 'bin', 'python3'), '');
    const { code, output } = await runScript(scratch);
    expect(code).toBe(254);
    expect(output).toContain('Missing required toolchain binary: .venv/bin/td');
    expect(output).toContain('setup-agent.sh');
  });

  it('resolves the pinned venv paths with no ambient fallback in source', () => {
    const source = fs.readFileSync(SCRIPT, 'utf8');
    expect(source).not.toContain('command -v');
    expect(source).not.toContain(`: 'python3'`);
    expect(source).not.toContain(`: 'td'`);
    expect(source).toContain(`'.venv/bin/python3'`);
    expect(source).toContain(`'.venv/bin/td'`);
  });
});
