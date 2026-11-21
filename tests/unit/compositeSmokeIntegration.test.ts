import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import yaml from 'yaml';

const action = yaml.parse(fs.readFileSync(path.resolve(__dirname, '../../.github/actions/impact-analysis/action.yml'), 'utf8'));
let root: string;
beforeEach(() => {
  root = fs.mkdtempSync(path.join(os.tmpdir(), 'composite-smoke-'));
  fs.mkdirSync(path.join(root, 'bin'));
  fs.writeFileSync(path.join(root, 'bin/gh'), '#!/bin/sh\nprintf "%s\\n" "$FAKE_GH_RESULT"\n', { mode: 0o755 });
  fs.writeFileSync(path.join(root, 'bin/docker'), '#!/bin/sh\nprintf "%s\\n" "$@" >> "$DOCKER_ARGS_FILE"\n', { mode: 0o755 });
});
afterEach(() => { fs.rmSync(root, { recursive: true, force: true }); });
function run(source: string, substitutions: Record<string, string>, extra: Record<string, string> = {}) {
  let script = source;
  for (const [expression, value] of Object.entries(substitutions)) script = script.replaceAll(expression, value);
  expect(script).not.toContain('${{');
  const file = path.join(root, 'step.sh');
  fs.writeFileSync(file, script);
  const result = spawnSync('bash', ['-e', file], { cwd: root, encoding: 'utf8', env: {
    PATH: `${path.join(root, 'bin')}:${process.env.PATH}`,
    GITHUB_OUTPUT: path.join(root, 'output'),
    DOCKER_ARGS_FILE: path.join(root, 'docker-args'),
    GITHUB_TOKEN: 'OFFLINE_TOKEN_FIXTURE',
    GITHUB_REPOSITORY: 'fixture/repository',
    ...extra,
  } });
  expect(result.status, result.stdout + result.stderr).toBe(0);
}
describe('actual composite shell integration, offline command spies', () => {
  it.each([
    ['123', '', '', '123'], ['', '456', '', '456'], ['', '', '789', '789'], ['', '', 'null', ''],
  ])('resolves event=%s input=%s lookup=%s', (event, input, lookup, expected) => {
    const step = action.runs.steps.find((entry: any) => entry.id === 'resolve-pr');
    expect(step.env.GITHUB_TOKEN).toBe('${{ inputs.github_token }}');
    run(step.run, {
      '${{ github.event.pull_request.number }}': event,
      '${{ inputs.pr-number }}': input,
      '${{ github.ref_name }}': 'fixture-branch',
    }, { FAKE_GH_RESULT: lookup });
    expect(fs.readFileSync(path.join(root, 'output'), 'utf8').trim()).toBe(`pr_number=${expected}`);
  });
  it('passes token, resolved PR, repo and real workspace mount into the deterministic container command', () => {
    const step = action.runs.steps.find((entry: any) => entry.name === 'Execute Impact Analysis in Container');
    expect(step.env.GITHUB_TOKEN).toBe('${{ inputs.github_token }}');
    expect(step.env.PR_NUMBER).toBe('${{ steps.resolve-pr.outputs.pr_number }}');
    run(step.run, {
      '${{ github.workspace }}': '/fixture/workspace',
      '${{ inputs.container_image }}': 'fixture-image:exact-sha',
    }, { PR_NUMBER: '123', GEMINI_API_KEY: '', OPENAI_API_KEY: '' });
    const args = fs.readFileSync(path.join(root, 'docker-args'), 'utf8').trim().split('\n');
    expect(args).toContain('GITHUB_TOKEN=OFFLINE_TOKEN_FIXTURE');
    expect(args).toContain('PR_NUMBER=123');
    expect(args).toContain('GITHUB_REPOSITORY=fixture/repository');
    expect(args).toContain('/fixture/workspace:/github/workspace');
    expect(args).toContain('/github/workspace');
    expect(args).toContain('fixture-image:exact-sha');
    expect(args).toContain('/workspace/dist/impact.cjs');
    expect(args).not.toContain('/workspace/dist/runner.cjs');
    expect(args.filter(value => value === 'run')).toHaveLength(1);
  });
});
