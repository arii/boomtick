// fallow-ignore-file unused-file
// Reason: standalone node CLI entry point (run directly), not imported.
// Remote backend check: the extension reaches a backend on a NON-loopback address through the options page.
//   NODE_PATH=... PYTHONPATH=... node proofloop/extension/test/remote_backend_check.cjs [--bind-ip IP]
//
// The backend (harness/server.py) binds a non-loopback interface address (PROOFLOOP_BIND_HOST, default: this host's
// primary address) and accepts Host pl-backend.test:<port> via PROOFLOOP_ALLOWED_HOSTS. Chromium resolves
// pl-backend.test to that address, so traffic does not use loopback. Flow, through the shipped options page:
//   1. watched page with the default backend URL and no token -> pill "backend unavailable"
//   2. options: Backend URL http://pl-backend.test:<port>, token from that backend's state/server_token, Save
//   3. reload the page -> pill shows the live rules from that backend
// Headless Chromium cannot click the permission prompt, so the test copy of the extension declares the backend origin
// in host_permissions; the options Save handler still calls chrome.permissions.request, which then resolves true.
// The observer's closed shadow root is opened in the copy so the pill can be read.
// The rule set is a temporary TEST rule set in a temporary state directory, validated by the server like a real one.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const dgram = require('node:dgram');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { spawn, execFileSync } = require('node:child_process');
const { chromium } = (() => { try { return require('@playwright/test'); } catch { return require('playwright'); } })();

const root = path.resolve(__dirname, '../..');
const PORT = 8797;
const HOST = 'pl-backend.test';
const tmp = fs.mkdtempSync(path.join(process.env.PROOFLOOP_E2E_TMP || os.tmpdir(), 'proofloop-remote-'));
const RULES = { version: 'v3', parent: 'v2', instructions: [], page_rules: [
  { id: 'city-not-san-jose', kind: 'forbid_value', field: 'city', forbid: ['San Jose'], expect: 'San Francisco', tasks: ['event_registration'],
    message: 'Your sessions say San Francisco, not San Jose.', provenance: ['sess_2026_11_16_luma'] }] };

function primaryAddress() {
  return new Promise((resolve, reject) => {
    const s = dgram.createSocket('udp4');
    s.connect(1, '10.255.255.255', () => { const a = s.address().address; s.close(); resolve(a); });
    s.on('error', reject);
  });
}
const pill = (page) => page.evaluate(() => { const h = document.getElementById('proofloop-observer-host'); return h ? (h.shadowRoot.querySelector('.pill') || {}).textContent || null : 'not injected'; });
async function waitFor(fn, ms = 8000) { const end = Date.now() + ms; for (;;) { const v = await fn(); if (v) return v; if (Date.now() > end) throw new Error('timeout'); await new Promise((r) => setTimeout(r, 150)); } }

(async () => {
  const ip = process.argv.includes('--bind-ip') ? process.argv[process.argv.indexOf('--bind-ip') + 1] : await primaryAddress();
  assert.ok(!/^127\.|^::1$/.test(ip), `need a non-loopback address, got ${ip}`);

  const dir = path.join(tmp, 'ext');
  fs.cpSync(path.join(root, 'extension'), dir, { recursive: true, filter: (s) => !s.includes(`${path.sep}test`) });
  const { publicKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
  const der = publicKey.export({ type: 'spki', format: 'der' });
  const id = [...crypto.createHash('sha256').update(der).digest().subarray(0, 16)].map((b) => String.fromCharCode(97 + (b >> 4)) + String.fromCharCode(97 + (b & 15))).join('');
  const mf = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json'), 'utf8'));
  mf.key = der.toString('base64');
  mf.host_permissions.push(`http://${HOST}/*`, 'http://luma.com/*');
  fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify(mf));
  const o = path.join(dir, 'assist/observer.js');
  fs.writeFileSync(o, fs.readFileSync(o, 'utf8').replace('attachShadow({ mode: "closed" })', 'attachShadow({ mode: "open" })'));

  const state = path.join(tmp, 'state');
  fs.mkdirSync(state);
  const env = { ...process.env, PROOFLOOP_EXTENSION_ID: id, PROOFLOOP_STATE: state, PROOFLOOP_PRIVATE_DIR: path.join(tmp, 'private'),
    PROOFLOOP_LIVE_SERVICES: '', PROOFLOOP_BIND_HOST: ip, PROOFLOOP_ALLOWED_HOSTS: `${HOST}:${PORT}` };
  delete env.PROOFLOOP_TOKEN;
  const sha = execFileSync('python3', ['-c', 'import json,sys,rules;print(rules.sha256(json.loads(sys.argv[1])))', JSON.stringify(RULES)], { cwd: path.join(root, 'harness'), env }).toString().trim();
  fs.writeFileSync(path.join(state, 'active_rules.json'), JSON.stringify({ rules: RULES, sha256: sha, senso: {} }));
  const backend = spawn('python3', [path.join(root, 'harness/server.py'), String(PORT)], { env, stdio: ['ignore', 'pipe', 'pipe'] });
  let out = '';
  backend.stdout.on('data', (d) => (out += d));
  backend.stderr.on('data', (d) => (out += d));
  await waitFor(() => fs.existsSync(path.join(state, 'server_token')));
  const token = fs.readFileSync(path.join(state, 'server_token'), 'utf8').trim();

  const fx = http.createServer((req, res) => { res.setHeader('Content-Type', 'text/html'); res.end(fs.readFileSync(path.join(__dirname, 'fixtures/luma_registration.html'), 'utf8')); });
  await new Promise((r) => fx.listen(0, '127.0.0.1', r));
  const page_url = `http://luma.com:${fx.address().port}/personalagenthack`;
  const ctx = await chromium.launchPersistentContext(path.join(tmp, 'profile'), {
    channel: 'chromium', headless: true, env: { ...process.env, HOME: tmp },
    args: [`--disable-extensions-except=${dir}`, `--load-extension=${dir}`, `--host-resolver-rules=MAP ${HOST} ${ip}, MAP luma.com 127.0.0.1`] });
  const report = { backend_url: `http://${HOST}:${PORT}`, resolves_to: ip, server_log: '' };
  try {
    // Direct checks: the non-loopback address is reachable, and the Host allowlist is what admits it.
    const raw = (h) => new Promise((resolve) => { const r = http.request({ host: ip, port: PORT, path: '/status', headers: { Host: h, Authorization: `Bearer ${token}` } }, (x) => { x.resume(); resolve(x.statusCode); }); r.on('error', (e) => resolve(String(e.code))); r.end(); });
    report.direct = { [`Host ${HOST}:${PORT}`]: await raw(`${HOST}:${PORT}`), 'Host evil.example': await raw(`evil.example:${PORT}`), [`Host 127.0.0.1:${PORT} over ${ip}`]: await raw(`127.0.0.1:${PORT}`) };
    assert.equal(report.direct[`Host ${HOST}:${PORT}`], 200);
    assert.equal(report.direct['Host evil.example'], 403);

    const sw = ctx.serviceWorkers()[0] || await ctx.waitForEvent('serviceworker');
    await sw.evaluate(async (w) => { await chrome.storage.local.set({ watched: [w] }); await syncRegistrations(); }, new URL(page_url).origin);
    const page = await ctx.newPage();
    await page.goto(page_url);
    report.before = await waitFor(async () => { const p = await pill(page); return p && p !== 'not injected' && p; });
    assert.match(report.before, /backend unavailable/);

    const opt = await ctx.newPage();
    await opt.goto(`chrome-extension://${id}/options.html`);
    await opt.waitForTimeout(500);
    report.options_status_before = (await opt.textContent('#status')).trim().slice(0, 120);
    await opt.fill('#backend_url', `http://${HOST}:${PORT}/some/path?ignored=1`);
    await opt.fill('#token', token);
    await opt.click('#save');
    report.options_msg = await waitFor(async () => (await opt.textContent('#msg')).trim());
    report.stored = await sw.evaluate(() => chrome.storage.local.get(['backend_url']));
    assert.equal(report.stored.backend_url, `http://${HOST}:${PORT}`, 'URL normalized to its origin');
    await opt.reload();
    report.options_status_after = await waitFor(async () => { const t = (await opt.textContent('#status')).trim(); return !/Checking/.test(t) && t; });
    assert.doesNotMatch(report.options_status_after, /unavailable/);

    await page.reload();
    report.after = await waitFor(async () => { const p = await pill(page); return p && /rule/.test(p) && p; });
    await page.fill('#_r_n_', 'San Jose');
    report.after_typing = await waitFor(async () => { const p = await pill(page); return /conflict/.test(p || '') && p; });
    console.log(JSON.stringify(report, null, 1));
    console.log('remote backend check passed');
  } finally {
    report.server_log = out.trim();
    if (process.exitCode) console.log(report.server_log);
    await ctx.close(); fx.close(); backend.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
})().catch((e) => { console.error(e); process.exit(1); });
