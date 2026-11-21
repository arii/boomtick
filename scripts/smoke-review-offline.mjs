#!/usr/bin/env node
// Offline assertions about real bundled programs, never an AI review approval.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const bundleDir = path.resolve(process.argv[2] || path.join(path.dirname(fileURLToPath(import.meta.url)), '../dist'));
for (const file of ['runner.cjs', 'impact.cjs']) assert.ok(fs.existsSync(path.join(bundleDir, file)), `Missing bundle: ${file}`);
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'boomtick-offline-smoke-'));
const env = {
  PATH: process.env.PATH,
  HOME: root,
  GIT_CONFIG_NOSYSTEM: '1',
  GIT_CONFIG_GLOBAL: '/dev/null',
  GITHUB_BASE_REF: 'smoke-base',
};
function run(program, args = [], extraEnv = {}) {
  const result = spawnSync(process.execPath, [...args, path.join(bundleDir, program), 'gemini'], {
    cwd: root, env: { ...env, ...extraEnv }, encoding: 'utf8', timeout: 30000,
  });
  if (result.error) throw result.error;
  return result;
}
function verdict() { return JSON.parse(fs.readFileSync(path.join(root, 'artifacts/gemini-code-review-verdict.json'), 'utf8')); }
function git(...args) { return execFileSync('git', args, { cwd: root, env, encoding: 'utf8' }); }
try {
  fs.mkdirSync(path.join(root, 'src'));
  fs.writeFileSync(path.join(root, '.dependency-cruiser.config.mjs'), 'export default {};\n');
  fs.writeFileSync(path.join(root, 'tsconfig.app.json'), '{"compilerOptions":{"moduleResolution":"node"}}\n');
  fs.writeFileSync(path.join(root, 'src/b.ts'), 'export const b = 1;\n');
  fs.writeFileSync(path.join(root, 'src/a.ts'), "import { b } from './b'; export const a = b;\n");
  fs.writeFileSync(path.join(root, 'src/c.ts'), "import { a } from './a'; console.log(a);\n");
  git('init', '-b', 'main');
  git('add', '.');
  git('-c', 'user.name=Offline Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'base');
  git('branch', 'smoke-base');
  fs.writeFileSync(path.join(root, 'src/b.ts'), 'export const b = 2;\n');
  git('add', '.');
  git('-c', 'user.name=Offline Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'candidate');

  // Preload into the actual runner, not production code. No provider traffic is allowed.
  fs.writeFileSync(path.join(root, 'deny-network.cjs'), `
const fs = require('node:fs');
global.fetch = async () => {
  fs.appendFileSync('offline-boundary.log', 'blocked before fetch\\n');
  throw new Error('OFFLINE_SENTINEL: no network allowed');
};
`);
  const guard = ['--require', path.join(root, 'deny-network.cjs')];
  const impact = run('impact.cjs', guard, { CHANGED_FILES: 'src/b.ts' });
  assert.equal(impact.status, 0, impact.stdout + impact.stderr);
  const report = JSON.parse(fs.readFileSync(path.join(root, 'artifacts/impact-analysis.json'), 'utf8'));
  assert.ok(report.changedFiles.includes('src/b.ts'));
  assert.ok(!fs.existsSync(path.join(root, 'offline-boundary.log')), 'Deterministic impact must not call a provider');

  const missing = run('runner.cjs', guard);
  assert.equal(missing.status, 1, missing.stdout + missing.stderr);
  assert.equal(verdict().passed, false);
  assert.equal(verdict().skipReason, 'MISSING_API_KEY');
  assert.ok(!fs.existsSync(path.join(root, 'offline-boundary.log')), 'Missing-key path must stop before fetch');

  const unavailable = run('runner.cjs', guard, { GEMINI_API_KEY: 'OFFLINE_SENTINEL' });
  assert.equal(unavailable.status, 1, unavailable.stdout + unavailable.stderr);
  assert.equal(verdict().passed, false);
  assert.notEqual(verdict().skipReason, 'PREPARATION_FAILED', 'Valid dependency context must reach the offline provider boundary');
  assert.ok(fs.existsSync(path.join(root, 'offline-boundary.log')), 'Expected provider boundary was never reached');
  fs.unlinkSync(path.join(root, 'offline-boundary.log'));

  // Mock only the HTTP boundary. The actual model picker, request builder,
  // response parser, specialist orchestration, aggregation and reports still run.
  fs.writeFileSync(path.join(root, 'mock-provider.cjs'), `
const fs = require('node:fs');
const assert = require('node:assert/strict');
let generated = 0;
global.fetch = async (url, options) => {
  const parsed = new URL(url);
  assert.equal(parsed.hostname, 'generativelanguage.googleapis.com');
  if (parsed.pathname === '/v1beta/models') {
    return { ok: true, json: async () => ({ models: [{ name: 'models/gemini-3.1-flash-lite' }] }) };
  }
  assert.ok(parsed.pathname.endsWith(':generateContent'));
  assert.equal(options.method, 'POST');
  const payload = JSON.parse(options.body);
  const text = payload.contents[0].parts.map(part => part.text || '').join(' ');
  assert.ok(text.includes('src/b.ts'), 'Real diff was not included');
  assert.ok(text.includes('Impacted (dependents): src/a.ts'), 'Native dependency context was not included');
  generated++;
  fs.appendFileSync('mock-requests.log', JSON.stringify({ generated, contextVerified: true }) + '\\n');
  const malformed = process.env.SMOKE_RESPONSE === 'partial' && generated === 1;
  const responseText = malformed ? 'unparseable fixture' : '[VERDICT: PASS] Offline test fixture, not real AI approval. <findings>{"findings":[]}</findings>';
  return {
    ok: true,
    json: async () => ({ candidates: [{ content: { parts: [{ text: responseText }] }, finishReason: 'STOP' }], usageMetadata: { promptTokenCount: 50, candidatesTokenCount: 20, totalTokenCount: 70 } }),
  };
};
`);
  const mockGuard = ['--require', path.join(root, 'mock-provider.cjs')];
  const success = run('runner.cjs', mockGuard, { GEMINI_API_KEY: 'OFFLINE_SENTINEL' });
  assert.equal(success.status, 0, success.stdout + success.stderr);
  assert.equal(verdict().passed, true);
  assert.equal(verdict().llmVerdict, 'pass');
  assert.equal(verdict().skipReason, undefined);
  assert.equal(fs.readFileSync(path.join(root, 'mock-requests.log'), 'utf8').trim().split('\n').length, 4, 'All four specialists must complete');
  assert.ok(fs.readFileSync(path.join(root, 'artifacts/gemini-code-review.md'), 'utf8').includes('Offline test fixture'));
  fs.unlinkSync(path.join(root, 'mock-requests.log'));
  const partial = run('runner.cjs', mockGuard, { GEMINI_API_KEY: 'OFFLINE_SENTINEL', SMOKE_RESPONSE: 'partial' });
  assert.equal(partial.status, 1, partial.stdout + partial.stderr);
  assert.equal(verdict().passed, false);
  assert.equal(verdict().skipReason, 'PARSE_ERROR');
  assert.equal(fs.readFileSync(path.join(root, 'mock-requests.log'), 'utf8').trim().split('\n').length, 4);

  fs.writeFileSync(path.join(root, 'artifacts/dependency-graph.json'), '{"modules":false}');
  const invalid = run('runner.cjs', guard, { GEMINI_API_KEY: 'OFFLINE_SENTINEL' });
  assert.equal(invalid.status, 1, invalid.stdout + invalid.stderr);
  assert.equal(verdict().passed, false);
  assert.equal(verdict().skipReason, 'PREPARATION_FAILED');
  assert.ok(!fs.existsSync(path.join(root, 'offline-boundary.log')), 'Invalid context must stop before fetch');

  console.log('PASS: real bundles, dependency context, all-four-specialist mocked success, partial/missing-key/context/provider failure.');
  console.log('Offline smoke only. No provider request or AI approval.');
} finally {
  fs.rmSync(root, { recursive: true, force: true });
}
