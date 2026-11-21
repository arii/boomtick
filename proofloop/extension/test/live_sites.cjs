// Live-site check (PLAN 2.1): the shipped observer on the real Luma registration dialog and the real Vouch Apply form.
//   NODE_PATH=... PYTHONPATH=... node proofloop/extension/test/live_sites.cjs            # uses your PROOFLOOP_STATE rule set
//   NODE_PATH=... PYTHONPATH=... node proofloop/extension/test/live_sites.cjs --test-rules   # temporary test rule set
//
// Safety: never fills name or email, never enters real personal data (the phone is a fictional 555 number), never
// clicks Vouch's "Start Application", and clicks Luma's "Request to Join" only while a conflict is open and with
// name and email empty, so Luma's own validation would refuse the form even if the hold failed. Nothing is submitted.
// Test-only changes to a COPY of the extension: fixed key, host permissions for the two sites (instead of the popup
// prompt), open shadow root for reading the UI. Screenshots go to PROOFLOOP_SHOTS (default: a temp dir).
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn, execFileSync } = require('node:child_process');
const { chromium } = (() => { try { return require('@playwright/test'); } catch { return require('playwright'); } })();

const root = path.resolve(__dirname, '../..');
const testRules = process.argv.includes('--test-rules');
const TOKEN = 'live-' + crypto.randomBytes(8).toString('hex');
const tmp = fs.mkdtempSync(path.join(process.env.PROOFLOOP_E2E_TMP || os.tmpdir(), 'proofloop-live-'));
const shots = process.env.PROOFLOOP_SHOTS || path.join(tmp, 'shots');
fs.mkdirSync(shots, { recursive: true });
const FAMILY = '415-555-0100';

const RULES = {
  version: 'v900', parent: null, instructions: [],
  page_rules: [
    { id: 'city-not-san-jose', kind: 'forbid_value', field: 'city', forbid: ['San Jose'], expect: 'San Francisco',
      tasks: ['event_registration', 'insurance_or_service_quote'], message: 'Your sessions say San Francisco, not San Jose.', provenance: ['sess_2026_11_16_vouch', 'sess_2026_11_16_luma'] },
    { id: 'no-sponsor-consent', kind: 'keep_unchecked', label_all: ['sponsor'], tasks: ['event_registration'],
      message: 'You did not want your contact info shared with sponsors.', provenance: ['sess_2026_11_16_luma'] },
    { id: 'phone-professional', kind: 'forbid_value', field: 'phone', forbid: ['[PHONE-FAMILY]'], expect: '[PHONE-PRO]',
      tasks: ['job_application', 'insurance_or_service_quote'], message: 'That is your friends and family number. Use your professional number.', provenance: ['sess_2026_11_18_waas'] },
  ],
};

function prepareExtension() {
  const dir = path.join(tmp, 'ext');
  fs.cpSync(path.join(root, 'extension'), dir, { recursive: true, filter: (s) => !s.includes(`${path.sep}test`) });
  const { publicKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
  const der = publicKey.export({ type: 'spki', format: 'der' });
  const id = [...crypto.createHash('sha256').update(der).digest().subarray(0, 16)].map((b) => String.fromCharCode(97 + (b >> 4)) + String.fromCharCode(97 + (b & 15))).join('');
  const mf = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json'), 'utf8'));
  mf.key = der.toString('base64');
  mf.host_permissions.push('https://luma.com/*', 'https://apply.vouch.us/*');
  fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify(mf));
  const o = path.join(dir, 'assist/observer.js');
  fs.writeFileSync(o, fs.readFileSync(o, 'utf8').replace('attachShadow({ mode: "closed" })', 'attachShadow({ mode: "open" })'));
  return { dir, id };
}

const ui = (page) => page.evaluate(() => {
  const h = document.getElementById('proofloop-observer-host');
  if (!h) return null;
  const r = h.shadowRoot, rect = (e) => { const b = e.getBoundingClientRect(); return { left: b.left, top: b.top, right: b.right, bottom: b.bottom }; };
  const vis = (e) => e.getClientRects().length > 0;
  return {
    pill: r.querySelector('.pill')?.textContent || null, pillRect: r.querySelector('.pill') ? rect(r.querySelector('.pill')) : null, panel: r.querySelector('.panel')?.innerText || null,
    chips: [...r.querySelectorAll('.chip')].map((c) => ({ text: c.innerText, rect: rect(c) })), outlines: r.querySelectorAll('.outline').length,
    controls: [...document.querySelectorAll('input,select,textarea,button')].filter(vis).filter((e) => { const b = e.getBoundingClientRect(); return b.width > 2 && b.height > 2; })
      .map((e) => ({ what: `${e.tagName.toLowerCase()} ${e.id || e.name || e.textContent.trim().slice(0, 30)}`, rect: rect(e) })),
  };
});
const overlaps = (a, b) => Math.min(a.right, b.right) > Math.max(a.left, b.left) && Math.min(a.bottom, b.bottom) > Math.max(a.top, b.top);
async function waitFor(fn, ms = 10000) { const end = Date.now() + ms; for (;;) { const v = await fn(); if (v) return v; if (Date.now() > end) throw new Error('timeout'); await new Promise((r) => setTimeout(r, 150)); } }
const noCover = (u) => { if (u.pillRect) for (const x of u.controls) assert.ok(!overlaps(u.pillRect, x.rect), `pill covers ${x.what}: pill ${JSON.stringify(u.pillRect)} control ${JSON.stringify(x.rect)}`); for (const c of u.chips) for (const x of u.controls) assert.ok(!overlaps(c.rect, x.rect), `chip covers ${x.what}: chip ${JSON.stringify(c.rect)} control ${JSON.stringify(x.rect)}`); };

(async () => {
  const { dir, id } = prepareExtension();
  const env = { ...process.env, PROOFLOOP_EXTENSION_ID: id, PROOFLOOP_TOKEN: TOKEN };
  if (testRules) {
    const state = path.join(tmp, 'state'), priv = path.join(tmp, 'private');
    fs.mkdirSync(state); fs.mkdirSync(priv);
    const sha = execFileSync('python3', ['-c', 'import json,sys,rules;print(rules.sha256(json.loads(sys.argv[1])))', JSON.stringify(RULES)], { cwd: path.join(root, 'harness'), env }).toString().trim();
    fs.writeFileSync(path.join(state, 'active_rules.json'), JSON.stringify({ rules: RULES, sha256: sha, scores: {}, senso: {} }));
    fs.writeFileSync(path.join(priv, 'values.json'), JSON.stringify({ '[PHONE-FAMILY]': FAMILY, '[PHONE-PRO]': '415-555-0142' }));
    Object.assign(env, { PROOFLOOP_STATE: state, PROOFLOOP_PRIVATE_DIR: priv, PROOFLOOP_LIVE_SERVICES: '' });
  }
  const backend = spawn('python3', [path.join(root, 'harness/server.py'), '8787'], { env, stdio: 'ignore' });
  await waitFor(async () => { try { return (await fetch('http://127.0.0.1:8787/')).ok; } catch { return false; } });
  const skill = await fetch('http://127.0.0.1:8787/skill', { headers: { Authorization: `Bearer ${TOKEN}` } });
  if (skill.status !== 200) { console.error(`BLOCKED: no promoted rule set in PROOFLOOP_STATE (GET /skill -> ${skill.status}). Run replay_loop.py first, or pass --test-rules.`); backend.kill(); process.exit(2); }
  const ctx = await chromium.launchPersistentContext(path.join(tmp, 'profile'), {
    channel: 'chromium', headless: true, env: { ...process.env, HOME: tmp }, viewport: { width: 1280, height: 800 },
    args: [`--disable-extensions-except=${dir}`, `--load-extension=${dir}`] });
  try {
    const sw = ctx.serviceWorkers()[0] || await ctx.waitForEvent('serviceworker');
    await sw.evaluate(async (t) => { await chrome.storage.local.set({ token: t, watched: ['https://luma.com', 'https://apply.vouch.us'] }); await syncRegistrations(); }, TOKEN);

    // ---- Luma
    const page = await ctx.newPage();
    const posts = [];
    page.on('request', (r) => { if (r.method() === 'POST' && /luma|lu\.ma/.test(new URL(r.url()).hostname) && /regist|rsvp|join|ticket|guest/i.test(r.url())) posts.push(r.url()); });
    await page.goto('https://luma.com/personalagenthack', { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'Request to Join' }).first().click();
    // After the event date Luma first asks "Past Event ... Proceed / Cancel"; Proceed only opens the same form.
    const proceed = page.getByRole('button', { name: 'Proceed' });
    if (await proceed.isVisible({ timeout: 3000 }).catch(() => false)) await proceed.click();
    const cityBox = page.getByLabel(/What city are you based in/);
    await cityBox.waitFor({ timeout: 15000 });
    await page.waitForTimeout(1500);
    let u = await waitFor(async () => { const x = await ui(page); return x && x.pill && x; });
    console.log('luma pill:', u.pill);
    assert.match(u.pill, /rule/);
    await cityBox.fill('San Jose');
    u = await waitFor(async () => { const x = await ui(page); return x && x.outlines >= 1 && x; });
    console.log('luma chip:', JSON.stringify(u.chips.map((c) => c.text)));
    noCover(u);
    assert.equal(await cityBox.inputValue(), 'San Jose');
    await page.screenshot({ path: path.join(shots, 'luma-city-warning.png') });
    await page.getByText(/consent to providing your contact information/).click();
    u = await waitFor(async () => { const x = await ui(page); return /2 conflicts/.test(x.pill || '') && x; });
    noCover(u);
    await page.screenshot({ path: path.join(shots, 'luma-two-conflicts.png') });
    // Submit attempt while conflicts are open (name and email are empty, so Luma would refuse anyway).
    await page.locator('[role=dialog] button[type=submit]').click();
    u = await waitFor(async () => { const x = await ui(page); return x.panel && /Before you submit/.test(x.panel) && x; });
    await page.waitForTimeout(1500);
    assert.deepEqual(posts, [], 'no registration request was sent while held');
    await page.screenshot({ path: path.join(shots, 'luma-submit-held.png') });
    await page.evaluate(() => [...document.getElementById('proofloop-observer-host').shadowRoot.querySelectorAll('.panel button')].find((b) => b.textContent === 'Back to form').click());
    // Dismiss the city warning from the panel, then make Luma re-render (type in another field, blur): it stays dismissed.
    const clickPanel = (p, text) => p.evaluate(() => { const r = document.getElementById('proofloop-observer-host').shadowRoot;
      if (!r.querySelector('.panel')) r.querySelector('.pill').click(); }, text).then(() => p.waitForTimeout(300)).then(() => p.evaluate((t) => {
      const b = [...document.getElementById('proofloop-observer-host').shadowRoot.querySelectorAll('.panel .card')].find((c) => c.innerText.includes(t));
      [...b.querySelectorAll('button')].find((x) => x.textContent === 'Got it').click(); }, text));
    await clickPanel(page, 'San Francisco, not San Jose');
    await page.getByLabel(/What company/).fill('Acme');
    await page.getByLabel(/What is your job title/).click();
    await page.waitForTimeout(2000);
    u = await ui(page);
    console.log('luma after dismiss + re-render:', u.pill, 'outlines', u.outlines);
    assert.match(u.pill, /1 conflict/, 'only the consent conflict remains');
    console.log('luma: warnings shown, nothing covered, submit held, no registration request, dismissal survives re-render');
    await page.close();

    // ---- Vouch (never clicks Start Application)
    const v = await ctx.newPage();
    await v.goto('https://apply.vouch.us/', { waitUntil: 'domcontentloaded' });
    await v.getByLabel('Phone Number').waitFor({ timeout: 15000 });
    await v.waitForTimeout(1500);
    await v.getByLabel('Phone Number').fill(FAMILY);
    const addr = v.locator('input[placeholder^="Street address"]');
    await addr.click();
    await addr.pressSequentially('1 Main St San Jose', { delay: 40 });
    const option = v.getByRole('option', { name: /San Jose, CA/ }).first();
    await option.waitFor({ timeout: 10000 });
    console.log('vouch picks suggestion:', await option.innerText());
    await option.click();
    await v.waitForTimeout(1500);
    console.log('vouch address value after pick:', await addr.inputValue());
    u = await waitFor(async () => { const x = await ui(v); return x && /2 conflicts/.test(x.pill || '') && x; });
    noCover(u);
    console.log('vouch pill:', u.pill, 'chips:', JSON.stringify(u.chips.map((c) => c.text)));
    // Dismiss the address warning, then open the Location Type dropdown (Vouch mounts a listbox): it stays dismissed.
    await clickPanel(v, 'San Francisco, not San Jose');
    await v.getByLabel(/Location Type/).click();
    await v.waitForTimeout(2000);
    const mounted = await v.locator('[role=listbox]').count();
    u = await ui(v);
    console.log('vouch after dismiss + dropdown (listboxes mounted:', mounted + '):', u.pill);
    assert.match(u.pill, /1 conflict/, 'only the phone conflict remains');
    await v.keyboard.press('Escape');
    await v.screenshot({ path: path.join(shots, 'vouch-two-conflicts.png') });
    console.log(`live sites passed (${testRules ? 'test rule set' : 'your promoted rule set'}). Screenshots: ${shots}`);
  } finally {
    await ctx.close();
    backend.kill();
    if (!process.env.PROOFLOOP_SHOTS) fs.rmSync(tmp, { recursive: true, force: true });
  }
})().catch((e) => { console.error(e.message || e); process.exit(1); });
