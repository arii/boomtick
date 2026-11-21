import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { getAIContext } from '../../lib/reviewContext';

const mocks = vi.hoisted(() => {
  const exec = vi.fn();
  Object.defineProperty(exec, Symbol.for('nodejs.util.promisify.custom'), { value: exec, configurable: true });
  return { exec };
});
vi.mock('node:child_process', () => ({ execFile: mocks.exec }));

let root: string;
let cwd: string;
const graph = { modules: [
  { source: 'src/a.ts', dependencies: [{ resolved: 'src/b.ts' }, {}] },
  { source: 'src/b.ts', dependencies: [] },
  { source: 'src/c.ts', dependencies: [{ resolved: 'src/a.ts' }] },
] };
const input = JSON.stringify({ files: [{ path: 'src/a.ts', diff: 'fixture' }, { path: 'src/b.ts' }, { path: '' }] });
const expected = [
  { path: 'src/a.ts', dependencies: ['src/b.ts'], dependents: ['src/c.ts'], semantic: [] },
  { path: 'src/b.ts', dependencies: [], dependents: ['src/a.ts'], semantic: [] },
];
beforeEach(() => {
  vi.clearAllMocks();
  cwd = process.cwd();
  root = fs.mkdtempSync(path.join(os.tmpdir(), 'review-context-'));
  process.chdir(root);
});
afterEach(() => { process.chdir(cwd); fs.rmSync(root, { recursive: true, force: true }); });
function configured() {
  fs.mkdirSync('src');
  fs.writeFileSync('.dependency-cruiser.config.mjs', 'export default {}');
  fs.writeFileSync('tsconfig.app.json', '{}');
}

describe('native registered get-context contract', () => {
  it('uses validated cached edges with the same direction and order as the CLI', async () => {
    fs.mkdirSync('artifacts');
    fs.writeFileSync('artifacts/dependency-graph.json', JSON.stringify(graph));
    expect(await getAIContext(input)).toEqual(expected);
    expect(mocks.exec).not.toHaveBeenCalled();
  });
  it('executes installed depcruise without a shell, Python, pnpm or download', async () => {
    configured();
    mocks.exec.mockResolvedValue({ stdout: JSON.stringify(graph) });
    expect(await getAIContext(input)).toEqual(expected);
    expect(mocks.exec).toHaveBeenCalledWith('depcruise', [
      'src', '--config', '.dependency-cruiser.config.mjs', '--ts-config', 'tsconfig.app.json', '--output-type', 'json',
    ], expect.objectContaining({ timeout: 60000 }));
    expect(fs.existsSync('artifacts/dependency-graph.json')).toBe(false);
  });
  it('matches the registered CLI missing-config behavior with an explicit warning', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    expect(await getAIContext(input)).toEqual(expected.map(entry => ({ ...entry, dependencies: [], dependents: [] })));
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('not applicable'));
    warn.mockRestore();
    expect(mocks.exec).not.toHaveBeenCalled();
  });
  it('rejects graph-tool failure and malformed output instead of substituting an empty graph', async () => {
    configured();
    mocks.exec.mockRejectedValueOnce(new Error('depcruise failed'));
    await expect(getAIContext(input)).rejects.toThrow('depcruise failed');
    mocks.exec.mockResolvedValueOnce({ stdout: 'not JSON' });
    await expect(getAIContext(input)).rejects.toThrow();
  });
  it.each([
    [], { modules: 'bad' }, { modules: [null] },
    { modules: [{ source: 1 }] }, { modules: [{ dependencies: {} }] },
    { modules: [{ dependencies: [null] }] }, { modules: [{ dependencies: [{ resolved: 1 }] }] },
  ])('rejects invalid cached graph %j', async (data) => {
    fs.mkdirSync('artifacts');
    fs.writeFileSync('artifacts/dependency-graph.json', JSON.stringify(data));
    await expect(getAIContext(input)).rejects.toThrow();
    expect(mocks.exec).not.toHaveBeenCalled();
  });
  it.each(['{', '{}', '[]', '{"files":{}}', '{"files":[null]}', '{"files":[{"path":1}]}'])(
    'rejects malformed request %s', async (data) => { await expect(getAIContext(data)).rejects.toThrow(); },
  );
  it('does not build a graph for an empty request', async () => {
    expect(await getAIContext('{"files":[]}')).toEqual([]);
    expect(mocks.exec).not.toHaveBeenCalled();
  });
});
