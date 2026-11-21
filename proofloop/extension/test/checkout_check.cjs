// Checkout check (follow-up 2): on a plain checkout page the observer must show no city or phone warning, while the
// same rules still fire on the Vouch form. Real Chromium, unpacked extension (fresh load), real backend.
//   NODE_PATH=... PYTHONPATH=... node proofloop/extension/test/checkout_check.cjs [--task-js PATH]
// --task-js swaps in another assist/task.js (used to show the behavior before the fix in 4728633).
// Page: the eval's checkout page (extension/test/eval/pages.json "checkout") at http://shop.example.test:<port>/checkout.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { spawn, execFileSync } = require('node:child_process');
const { chromium } = (() => { try { return require('@playwright/test'); } catch { return require('playwright'); } })();

const root = path.resolve(__dirname, '../..');
const taskJs = process.argv.includes('--task-js') ? process.argv[process.argv.indexOf('--task-js') + 1] : null;
const TOKEN = 'chk-' + crypto.randomBytes(8).toString('hex');
const tmp = fs.mkdtempSync(path.join(process.env.PROOFLOOP_E2E_TMP || os.tmpdir(), 'proofloop-chk-'));
const FAMILY = '415-555-0100';
const RULES = { version: 'v3', parent: 'v2', instructions: [], page_rules: [
  { id: 'city-not-san-jose', kind: 'forbid_value', field: 'city', forbid: ['San Jose'], expect: 'San Francisco', tasks: ['event_registration', 'insurance_or_service_quote'],
    message: 'Your sessions say San Francisco, not San Jose.', provenance: ['sess_2026_11_16_vouch', 'sess_2026_11_16_luma'] },
  { id: 'phone-professional', kind: 'forbid_value', field: 'phone', forbid: ['[PHONE-FAMILY]'], expect: '[PHONE-PRO]', tasks: ['job_application', 'insurance_or_service_quote'],
    message: 'That is your friends and family number. Use your professional number.', provenance: ['sess_2026_11_18_waas'] }] };
const pages = JSON.parse(fs.readFileSync(path.join(__dirname, 'eval/pages.json'), 'utf8'));

const ui = (page) => page.evaluate(() => {
  const h = document.getElementById('proofloop-observer-host');
  if (!h) return { injected: false };
  const r = h.shadowRoot;
  return { injected: true, pill: r.querySelector('.pill')?.textContent || null, chips: r.querySelectorAll('.chip').length, outlines: r.querySelectorAll('.outline').length };
});

(async () => {
  const dir = path.join(tmp, 'ext');
  fs.cpSync(path.join(root, 'extension'), dir, { recursive: true, filter: (s) => !s.includes(`${path.sep}test`) });
  if (taskJs) fs.copyFileSync(taskJs, path.join(dir, 'assist/task.js'));
  const { publicKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
  const der = publicKey.export({ type: 'spki', format: 'der' });
  const id = [...crypto.createHash('sha256').update(der).digest().subarray(0, 16)].map((b) => String.fromCharCode(97 + (b >> 4)) + String.fromCharCode(97 + (b & 15))).join('');
  const mf = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json'), 'utf8'));
  mf.key = der.toString('base64');
  mf.host_permissions.push('http://shop.example.test/*', 'http://apply.vouch.us/*');
  fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify(mf));
  const o = path.join(dir, 'assist/observer.js');
  fs.writeFileSync(o, fs.readFileSync(o, 'utf8').replace('attachShadow({ mode: "closed" })', 'attachShadow({ mode: "open" })'));

  const state = path.join(tmp, 'state'), priv = path.join(tmp, 'private');
  fs.mkdirSync(state); fs.mkdirSync(priv);
  const env = { ...process.env, PROOFLOOP_EXTENSION_ID: id, PROOFLOOP_TOKEN: TOKEN, PROOFLOOP_STATE: state, PROOFLOOP_PRIVATE_DIR: priv, PROOFLOOP_LIVE_SERVICES: '' };
  const sha = execFileSync('python3', ['-c', 'import json,sys,rules;print(rules.sha256(json.loads(sys.argv[1])))', JSON.stringify(RULES)], { cwd: path.join(root, 'harness'), env }).toString().trim();
  fs.writeFileSync(path.join(state, 'active_rules.json'), JSON.stringify({ rules: RULES, sha256: sha, senso: { node_id: 'node-chk', verified: true } }));
  fs.writeFileSync(path.join(priv, 'values.json'), JSON.stringify({ '[PHONE-FAMILY]': FAMILY, '[PHONE-PRO]': '415-555-0142' }));
  const backend = spawn('python3', [path.join(root, 'harness/server.py'), '8787'], { env, stdio: 'ignore' });
  for (let i = 0; i < 50; i++) { try { if ((await fetch('http://127.0.0.1:8787/')).ok) break; } catch { /* starting */ } await new Promise((r) => setTimeout(r, 100)); }

  const srv = http.createServer((req, res) => {
    res.setHeader('Content-Type', 'text/html');
    if ((req.headers.host || '').startsWith('apply.vouch.us')) return res.end(fs.readFileSync(path.join(__dirname, 'fixtures/vouch_apply.html'), 'utf8'));
    res.end(`<!doctype html><title>Checkout</title><body>${pages.checkout.html}</body>`);
  });
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  const port = srv.address().port;
  const ctx = await chromium.launchPersistentContext(path.join(tmp, 'profile'), {
    channel: 'chromium', headless: true, env: { ...process.env, HOME: tmp },
    args: [`--disable-extensions-except=${dir}`, `--load-extension=${dir}`, '--host-resolver-rules=MAP shop.example.test 127.0.0.1, MAP apply.vouch.us 127.0.0.1'] });
  const out = {};
  try {
    const sw = ctx.serviceWorkers()[0] || await ctx.waitForEvent('serviceworker');
    await sw.evaluate(async ([t, w]) => { await chrome.storage.local.set({ token: t, watched: w }); await syncRegistrations(); },
      [TOKEN, [`http://shop.example.test:${port}`, `http://apply.vouch.us:${port}`]]);

    const c = await ctx.newPage();
    const url = `http://shop.example.test:${port}/checkout`;
    await c.goto(url); await c.waitForTimeout(900);
    await c.fill('#city', 'San Jose');
    await c.fill('#phone', FAMILY);
    await c.fill('#street', '1 South Main Street, San Jose, CA 95112');
    await c.waitForTimeout(2500);
    out.checkout = { url, typed: { city: 'San Jose', phone: FAMILY, street: '1 South Main Street, San Jose, CA 95112' }, ...(await ui(c)) };

    const v = await ctx.newPage();
    await v.goto(`http://apply.vouch.us:${port}/`); await v.waitForTimeout(900);
    await v.fill('[id=":re:"]', FAMILY);
    await v.fill('[id=":r3:"]', '1 South Main Street, San Jose, CA 95112');
    await v.waitForTimeout(2500);
    out.vouch_control = { url: `http://apply.vouch.us:${port}/`, ...(await ui(v)) };
    console.log(JSON.stringify(out, null, 1));
    if (!taskJs) {
      assert.ok(out.checkout.injected, 'observer injected on the checkout page');
      assert.equal(out.checkout.chips + out.checkout.outlines, 0, 'no warning on checkout');
      assert.doesNotMatch(out.checkout.pill || '', /conflict/);
      assert.match(out.vouch_control.pill || '', /2 conflicts/, 'same rules still fire on Vouch');
      console.log('checkout check passed');
    }
  } finally {
    await ctx.close(); srv.close(); backend.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
})().catch((e) => { console.error(e); process.exit(1); });
