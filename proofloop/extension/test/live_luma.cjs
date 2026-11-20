// Live check against the real Luma registration dialog. Opens the page, clicks "Request to Join", types into the
// city question and checks the chip. It never submits the form and never fills name or email.
//   NODE_PATH=... PYTHONPATH=... node proofloop/extension/test/live_luma.cjs [URL]
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
// The repo pins @playwright/test; a standalone playwright install also works.
const { chromium } = (() => { try { return require('@playwright/test'); } catch { return require('playwright'); } })();

const root = path.resolve(__dirname, '../..');
const URL_ = process.argv[2] || 'https://luma.com/personalagenthack';
const TOKEN = 'live-' + crypto.randomBytes(8).toString('hex');
const tmp = fs.mkdtempSync(path.join(process.env.PROOFLOOP_E2E_TMP || os.tmpdir(), 'proofloop-live-'));

(async () => {
  const dir = path.join(tmp, 'ext');
  fs.cpSync(path.join(root, 'extension'), dir, { recursive: true, filter: (s) => !s.includes('/test/') });
  const { publicKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
  const der = publicKey.export({ type: 'spki', format: 'der' });
  const id = [...crypto.createHash('sha256').update(der).digest().subarray(0, 16)].map((b) => String.fromCharCode(97 + (b >> 4)) + String.fromCharCode(97 + (b & 15))).join('');
  const mf = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json'), 'utf8'));
  mf.key = der.toString('base64'); // shipped match patterns unchanged
  fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify(mf));
  const a = path.join(dir, 'assist/assist.js');
  fs.writeFileSync(a, fs.readFileSync(a, 'utf8').replace('attachShadow({ mode: "closed" })', 'attachShadow({ mode: "open" })'));

  const backend = spawn('python3', [path.join(root, 'harness/server.py'), '8787'], {
    env: { ...process.env, PROOFLOOP_EXTENSION_ID: id, PROOFLOOP_TOKEN: TOKEN, PROOFLOOP_STATE: path.join(tmp, 'state') }, stdio: 'ignore' });
  const ctx = await chromium.launchPersistentContext(path.join(tmp, 'profile'), {
    channel: 'chromium', headless: true, env: { ...process.env, HOME: tmp },
    args: [`--disable-extensions-except=${dir}`, `--load-extension=${dir}`] });
  try {
    await new Promise((r) => setTimeout(r, 1500));
    const sw = ctx.serviceWorkers()[0] || await ctx.waitForEvent('serviceworker');
    await sw.evaluate((t) => chrome.storage.local.set({ token: t }), TOKEN);
    const page = await ctx.newPage();
    await page.goto(URL_, { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'Request to Join' }).click();
    const city = page.getByLabel(/What city are you based in/);
    await city.waitFor({ timeout: 15000 });
    await city.fill('San Jose');
    await page.waitForTimeout(1200);
    const text = await page.evaluate(() => { const h = document.getElementById('proofloop-assist-host'); return h && h.style.display !== 'none' ? h.shadowRoot.querySelector('.chip').innerText : null; });
    assert.ok(text, 'chip did not appear on the live Luma dialog');
    assert.match(text, /rule\.city\.sf/);
    await page.screenshot({ path: path.join(root, '..', '..', '.kiro/artifacts/screenshots/luma-live-chip.png') }).catch(() => {});
    await page.evaluate(() => [...document.getElementById('proofloop-assist-host').shadowRoot.querySelectorAll('button')].find((b) => b.textContent.startsWith('Use')).click());
    const after = await city.inputValue();
    assert.equal(after, 'San Francisco');
    // React re-render check: blur and refocus; Luma's own state must keep the fixed value.
    await page.getByLabel(/What company/).focus();
    await page.waitForTimeout(400);
    assert.equal(await city.inputValue(), 'San Francisco', 'Luma kept the fixed value after blur');
    console.log('live Luma passed:', JSON.stringify(text));
  } finally {
    await ctx.close();
    backend.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
})().catch((e) => { console.error(e); process.exit(1); });
