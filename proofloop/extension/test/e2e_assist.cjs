// End-to-end: real Chromium with the unpacked extension, the real backend (harness/server.py) and form fixtures
// re-captured from the live Luma and Vouch pages.
//   NODE_PATH=<dir with playwright> PYTHONPATH=<dir with jsonschema> node proofloop/extension/test/e2e_assist.cjs
//
// The rule set below is TEST DATA written into a temporary state directory as if the loop had promoted it; it is
// validated by the server like a real one (schema, grounding in data/sessions.jsonl, hash). The private phone value
// is a test number in a temporary PROOFLOOP_PRIVATE_DIR. Test-only changes to a COPY of the extension: a fixed key
// (known extension ID), host permissions for the fixture hosts (instead of the popup's permission prompt), and an
// open shadow root so Playwright can read the UI. Shipped files are untouched.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = (() => { try { return require('@playwright/test'); } catch { return require('playwright'); } })();

const root = path.resolve(__dirname, '../..');
const TOKEN = 'e2e-' + crypto.randomBytes(8).toString('hex');
const PORT = 8787;
const tmp = fs.mkdtempSync(path.join(process.env.PROOFLOOP_E2E_TMP || os.tmpdir(), 'proofloop-e2e-'));
const HOSTS = ['luma.com', 'apply.vouch.us', 'profile.example', 'other.example'];
const FAMILY = '415-555-0100', PRO = '415-555-0142';

const RULES = {
  version: 'v3', parent: 'v2', instructions: [],
  page_rules: [
    { id: 'city-not-san-jose', kind: 'forbid_value', field: 'city', forbid: ['San Jose'], expect: 'San Francisco',
      tasks: ['event_registration', 'insurance_or_service_quote'], message: 'Your sessions say San Francisco, not San Jose.', provenance: ['sess_2026_11_16_vouch', 'sess_2026_11_16_luma'] },
    { id: 'no-sponsor-consent', kind: 'keep_unchecked', label_all: ['sponsor'], tasks: ['event_registration'],
      message: 'You did not want your contact info shared with sponsors.', provenance: ['sess_2026_11_16_luma'] },
    { id: 'phone-professional', kind: 'forbid_value', field: 'phone', forbid: ['[PHONE-FAMILY]'], expect: '[PHONE-PRO]',
      tasks: ['job_application', 'insurance_or_service_quote'], message: 'That is your friends and family number. Use your professional number.', provenance: ['sess_2026_11_18_waas'] },
  ],
};

function writeRules(rules, extra = {}) {
  const text = execPy(`import json,sys,rules;r=json.loads(sys.argv[1]);print(rules.sha256(r))`, JSON.stringify(rules));
  fs.writeFileSync(path.join(tmp, 'state', 'active_rules.json'), JSON.stringify({ rules, sha256: text, scores: { train: 1, holdout: 1 }, senso: { node_id: 'node-e2e', verified: true }, ...extra }));
}
function execPy(code, arg) {
  return require('node:child_process').execFileSync('python3', ['-c', code, arg], { cwd: path.join(root, 'harness'), env: process.env }).toString().trim();
}

function prepareExtension() {
  const dir = path.join(tmp, 'ext');
  fs.cpSync(path.join(root, 'extension'), dir, { recursive: true, filter: (s) => !s.includes(`${path.sep}test`) });
  const { publicKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
  const der = publicKey.export({ type: 'spki', format: 'der' });
  const id = [...crypto.createHash('sha256').update(der).digest().subarray(0, 16)].map((b) => String.fromCharCode(97 + (b >> 4)) + String.fromCharCode(97 + (b & 15))).join('');
  const mf = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json'), 'utf8'));
  mf.key = der.toString('base64');
  mf.host_permissions.push(...HOSTS.map((h) => `http://${h}/*`));
  fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify(mf));
  const o = path.join(dir, 'assist/observer.js');
  fs.writeFileSync(o, fs.readFileSync(o, 'utf8').replace('attachShadow({ mode: "closed" })', 'attachShadow({ mode: "open" })'));
  return { dir, id };
}

function startFixtures() {
  const fx = path.join(root, 'extension/test/fixtures');
  // Page-side probes stand in for the site's own handlers: they count submits/clicks that reach the page.
  const probe = `<script>window.__submits=0;window.__starts=0;document.addEventListener("submit",e=>{e.preventDefault();window.__submits++});
    document.addEventListener("click",e=>{const b=e.target.closest("button");if(b&&/Start Application/.test(b.textContent))window.__starts++})</script>`;
  const profile = '<!doctype html><title>Edit profile - Settings</title><h1>Edit profile</h1><form><label>Phone number <input type="tel" id="p"></label><button type="button">Save changes</button></form>';
  const srv = http.createServer((req, res) => {
    const host = (req.headers.host || '').split(':')[0];
    res.setHeader('Content-Type', 'text/html');
    if (host === 'profile.example') return res.end(profile);
    const f = host === 'apply.vouch.us' ? 'vouch_apply.html' : 'luma_registration.html';
    res.end(fs.readFileSync(path.join(fx, f), 'utf8') + probe);
  });
  return new Promise((r) => srv.listen(0, '127.0.0.1', () => r(srv)));
}

function startBackend(extId) {
  const p = spawn('python3', [path.join(root, 'harness/server.py'), String(PORT)], {
    env: { ...process.env, PROOFLOOP_EXTENSION_ID: extId, PROOFLOOP_TOKEN: TOKEN, PROOFLOOP_STATE: path.join(tmp, 'state'),
      PROOFLOOP_PRIVATE_DIR: path.join(tmp, 'private'), PROOFLOOP_LIVE_SERVICES: '' },
    stdio: ['ignore', 'ignore', 'pipe'],
  });
  let err = '';
  p.stderr.on('data', (d) => (err += d));
  p.errText = () => err;
  return p;
}
const up = async () => waitFor(async () => { try { return (await fetch(`http://127.0.0.1:${PORT}/`)).ok; } catch { return false; } });

async function waitFor(fn, ms = 7000) {
  const end = Date.now() + ms;
  for (;;) { const v = await fn(); if (v) return v; if (Date.now() > end) throw new Error('timeout waiting'); await new Promise((r) => setTimeout(r, 100)); }
}

// Reads of the observer's shadow UI.
const ui = (page) => page.evaluate(() => {
  const h = document.getElementById('proofloop-observer-host');
  if (!h) return null;
  const r = h.shadowRoot;
  const rect = (e) => { const b = e.getBoundingClientRect(); return { left: b.left, top: b.top, right: b.right, bottom: b.bottom }; };
  return {
    pill: r.querySelector('.pill')?.textContent || null,
    chips: [...r.querySelectorAll('.chip')].map((c) => ({ text: c.innerText, rect: rect(c) })),
    panel: r.querySelector('.panel')?.innerText || null,
    outlines: r.querySelectorAll('.outline').length,
    inputs: [...document.querySelectorAll('input,select,textarea')].filter((e) => e.getClientRects().length).map((e) => ({ id: e.id || e.type, rect: rect(e) })),
    buttons: [...document.querySelectorAll('button')].filter((e) => e.getClientRects().length).map((e) => ({ id: 'button ' + e.textContent.trim(), rect: rect(e) })),
  };
});
const clickUI = (page, text, scope = '') => page.evaluate(([t, s]) => {
  const b = [...document.getElementById('proofloop-observer-host').shadowRoot.querySelectorAll(`${s} button`)].find((x) => x.textContent.startsWith(t));
  if (!b) throw new Error('no button ' + t);
  b.click();
}, [text, scope]);
const overlaps = (a, b) => Math.min(a.right, b.right) > Math.max(a.left, b.left) && Math.min(a.bottom, b.bottom) > Math.max(a.top, b.top);

(async () => {
  fs.mkdirSync(path.join(tmp, 'state'), { recursive: true });
  fs.mkdirSync(path.join(tmp, 'private'), { recursive: true });
  fs.writeFileSync(path.join(tmp, 'private', 'values.json'), JSON.stringify({ '[PHONE-FAMILY]': FAMILY, '[PHONE-PRO]': PRO }));
  const { dir, id } = prepareExtension();
  let backend = startBackend(id);
  await up();
  const fixtures = await startFixtures();
  const fport = fixtures.address().port;
  const url = (host, p = '/') => `http://${host}:${fport}${p}`;
  const ctx = await chromium.launchPersistentContext(path.join(tmp, 'profile'), {
    channel: 'chromium', headless: true, env: { ...process.env, HOME: tmp }, viewport: { width: 1280, height: 900 },
    args: [`--disable-extensions-except=${dir}`, `--load-extension=${dir}`, `--host-resolver-rules=${HOSTS.map((h) => `MAP ${h} 127.0.0.1`).join(', ')}`],
  });
  const results = [];
  const step = async (name, fn) => { await fn(); results.push(name); console.log('ok -', name); };
  try {
    const sw = ctx.serviceWorkers()[0] || await ctx.waitForEvent('serviceworker');
    assert.equal(new URL(sw.url()).host, id);
    const watched = ['luma.com', 'apply.vouch.us', 'profile.example'].map((h) => new URL(url(h)).origin);
    await sw.evaluate(async ([t, w]) => { await chrome.storage.local.set({ token: t, watched: w, cross_tab: true }); await syncRegistrations(); }, [TOKEN, watched]);
    const open = async (u) => { const p = await ctx.newPage(); await p.goto(u); await p.waitForTimeout(900); return p; };
    const city = '#_r_n_';

    await step('no promoted rule set: typing San Jose shows no warning', async () => {
      const page = await open(url('luma.com', '/personalagenthack'));
      await page.fill(city, 'San Jose');
      await page.waitForTimeout(1000);
      const u = await ui(page);
      assert.ok(u, 'observer injected on a watched site');
      assert.equal(u.chips.length, 0);
      await page.close();
    });

    writeRules(RULES);
    let page;
    await step('promoted v3: task detected, pill lists the rules for event registration', async () => {
      page = await open(url('luma.com', '/personalagenthack'));
      const u = await waitFor(async () => { const x = await ui(page); return x && x.pill && x; });
      assert.match(u.pill, /2 rules/, u.pill);
    });

    await step('typing San Jose: inline warning with rule, version, Senso source and sessions; value untouched', async () => {
      await page.fill(city, 'San Jose');
      const u = await waitFor(async () => { const x = await ui(page); return x.chips.length && x; }).catch(async (e) => { console.error('UI at timeout:', JSON.stringify(await ui(page))); throw e; });
      assert.match(u.chips[0].text, /Your sessions say San Francisco, not San Jose\./);
      assert.match(u.chips[0].text, /Rule city-not-san-jose · v3 · Senso rule \(local copy\) · from sessions 11\/16, 11\/16/);
      assert.equal(await page.inputValue(city), 'San Jose', 'observer never changes the field');
      for (const i of u.inputs) assert.ok(!overlaps(u.chips[0].rect, i.rect), `chip covers input ${i.id}`);
      assert.match(u.pill, /1 conflict/);
    });

    await step('a value set by script (no input event) is caught by polling', async () => {
      await page.fill(city, '');
      await waitFor(async () => (await ui(page)).chips.length === 0);
      await page.evaluate((sel) => { const e = document.querySelector(sel); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(e, 'san josé, CA'); }, city);
      await waitFor(async () => (await ui(page)).chips.length === 1, 3000);
    });

    await step('near misses do not warn', async () => {
      for (const v of ['San Francisco', 'San Jose Street', 'North San Jose']) {
        await page.fill(city, v);
        await page.waitForTimeout(1000);
        assert.equal((await ui(page)).chips.length, 0, v);
      }
      await page.fill('#_r_k_', 'San Jose');
      await page.waitForTimeout(1000);
      assert.equal((await ui(page)).chips.length, 0, 'company field is not a city field');
    });

    await step('sponsor-consent box checked: conflict; submit is held and does not reach the page', async () => {
      // Dummy values for the other required fields so the browser's own validation does not block submits.
      for (const [sel, v] of [['#_r_c_', 'Test Person'], ['#_r_d_', 'test@example.com'], ['#_r_e_', 'Builder'], ['#_r_k_', 'Acme'], ['#_r_l_', 'Engineer'], ['#_r_m_', 'test@example.com'], ['#_r_o_', 'https://example.com/in/test']]) await page.fill(sel, v);
      await page.locator('input[type=checkbox]').nth(0).check();
      await page.fill(city, 'San Jose');
      await page.locator('input[type=checkbox]').nth(1).check();
      const two = await waitFor(async () => { const x = await ui(page); return /2 conflicts/.test(x.pill) && x; });
      assert.ok(two.chips.length >= 1, 'at least one inline chip');
      assert.equal(two.outlines, 2, 'both fields outlined');
      for (const c of two.chips) for (const r of two.inputs.concat(two.buttons)) assert.ok(!overlaps(c.rect, r.rect), `chip covers ${r.id}: ${JSON.stringify({ chips: two.chips.map((x) => x.rect), r: r.rect })}`);
      if (two.chips.length === 2) assert.ok(!overlaps(two.chips[0].rect, two.chips[1].rect), 'chips overlap each other');
      await page.getByRole('button', { name: 'Request to Join' }).last().click();
      const u = await waitFor(async () => { const x = await ui(page); return x.panel && x; });
      assert.match(u.panel, /Before you submit/);
      assert.match(u.panel, /contact info shared with sponsors/);
      assert.equal(await page.evaluate(() => window.__submits), 0, 'held submit never reached the page');
      await clickUI(page, 'Back to form', '.panel');
      assert.equal(await page.evaluate(() => window.__submits), 0);
    });

    await step('Got it and Rule is wrong dismiss; the next submit goes through; feedback recorded without values', async () => {
      await clickUI(page, 'ProofLoop');  // open the panel (Context & Rules)
      await waitFor(async () => (await ui(page)).panel);
      await clickUI(page, 'Got it', '.panel');
      await page.waitForTimeout(400);
      await clickUI(page, 'Rule is wrong', '.panel');
      await waitFor(async () => { const x = await ui(page); return x.chips.length === 0 && x.outlines === 0; }).catch(async (e) => { console.error('UI:', JSON.stringify(await ui(page)).slice(0, 1500)); throw e; });
      await page.getByRole('button', { name: 'Request to Join' }).last().click();
      await waitFor(async () => (await page.evaluate(() => window.__submits)) === 1).catch(async (e) => { console.error('UI2:', JSON.stringify(await ui(page)).slice(0, 900), await page.evaluate(() => [window.__submits, document.querySelectorAll('form').length, [...document.querySelectorAll('button')].map(b=>b.type+':'+b.textContent.trim())])); throw e; });
      const lines = await waitFor(() => { try { return fs.readFileSync(path.join(tmp, 'state', 'feedback.jsonl'), 'utf8').trim().split('\n'); } catch { return false; } });
      const acts = lines.map((l) => JSON.parse(l).action);
      for (const a of ['shown', 'dismissed', 'rule_wrong']) assert.ok(acts.includes(a), acts.join());
      assert.ok(!/San Jose|415/.test(lines.join('')));
      assert.equal(await page.inputValue(city), 'San Jose', 'still untouched');
    });

    await step('a dismissed warning stays dismissed when the page adds a field above it (React-style re-render)', async () => {
      await page.fill(city, 'San Jose, US');
      const before = await waitFor(async () => { const x = await ui(page); return x.chips.length === 1 && x; });
      await clickUI(page, 'Got it', '.chip');
      await waitFor(async () => (await ui(page)).chips.length === 0);
      const shownBefore = fs.readFileSync(path.join(tmp, 'state', 'feedback.jsonl'), 'utf8').split('\n').filter((l) => l.includes('"shown"')).length;
      // The site inserts a new labeled field at the top of the form, then re-renders: every field index shifts.
      await page.evaluate(() => { const f = document.querySelector('form'); const l = document.createElement('label'); l.textContent = 'Pronouns '; l.append(document.createElement('input')); f.prepend(l); });
      await page.waitForTimeout(1500);
      const after = await ui(page);
      assert.equal(after.chips.length + after.outlines, 0, 'dismissed warning came back after a re-render');
      const shownAfter = fs.readFileSync(path.join(tmp, 'state', 'feedback.jsonl'), 'utf8').split('\n').filter((l) => l.includes('"shown"')).length;
      assert.equal(shownAfter, shownBefore, '"shown" feedback re-sent for the same warning');
      assert.ok(before.chips.length === 1);
    });

    await step('Submit anyway releases a held submit once', async () => {
      await page.fill(city, 'SJ, CA');
      await page.fill(city, 'San Jose, CA');
      await waitFor(async () => (await ui(page)).chips.length === 1);
      await page.getByRole('button', { name: 'Request to Join' }).last().click();
      await waitFor(async () => (await ui(page)).panel);
      await clickUI(page, 'Submit anyway', '.panel');
      await waitFor(async () => (await page.evaluate(() => window.__submits)) === 2);
      await page.close();
    });

    let profile;
    await step('Vouch fixture: insurance task, family phone and San Jose address flagged; Start Application (type=button) held', async () => {
      profile = await open(url('profile.example', '/settings'));
      await profile.fill('#p', PRO);
      await profile.waitForTimeout(1200);
      page = await open(url('apply.vouch.us'));
      await page.fill('[id=":re:"]', FAMILY);
      await page.fill('[id=":r3:"]', '1 South Main Street, San Jose, CA');
      // 3 = family phone + San Jose address + phone differing from the profile tab (cross-tab is on in this test).
      await waitFor(async () => { const x = await ui(page); return x && /3 conflicts/.test(x.pill || '') && x.outlines === 2; }).catch(async (e) => { console.error('UI3:', JSON.stringify(await ui(page)).slice(0, 800)); throw e; });
      await clickUI(page, 'ProofLoop');
      const u = await waitFor(async () => { const x = await ui(page); return x.panel && x; });
      const texts = u.panel;
      assert.match(texts, /friends and family number/);
      assert.match(texts, /found: \[PHONE-FAMILY\]; your sessions say \[PHONE-PRO\]/);
      assert.match(texts, /San Francisco, not San Jose/);
      assert.ok(!texts.includes('415'), 'real numbers are never shown');
      await page.getByRole('button', { name: 'Start Application' }).click();
      const held = await waitFor(async () => { const x = await ui(page); return x.panel && x; });
      assert.equal(await page.evaluate(() => window.__starts), 0);
      assert.match(held.panel, /Your other tab "Edit profile - Settings" has a different phone \(ends 0142\)/);
      assert.match(held.panel, /From past sessions|Rules for this task/);
    });

    await step('unwatched site: nothing injected', async () => {
      const p = await open(url('other.example', '/personalagenthack'));
      await p.fill(city, 'San Jose');
      await p.waitForTimeout(800);
      assert.equal(await ui(p), null);
      await p.close();
    });

    await step('backend down: cached rules still warn, labeled cached', async () => {
      backend.kill(); await new Promise((r) => backend.once('exit', r));
      const p = await open(url('luma.com', '/personalagenthack'));
      await p.fill(city, 'San Jose');
      const u = await waitFor(async () => { const x = await ui(p); return x && x.chips.length && x; });
      assert.match(u.chips[0].text, /cached/);
      await p.close();
    });

    await step('markup in a rule message renders as text', async () => {
      const evil = JSON.parse(JSON.stringify(RULES));
      evil.page_rules[0].message = '<img src=x onerror="window.__pwned=1"><b>bold</b> San Jose';
      writeRules(evil);
      backend = startBackend(id);
      await up();
      await sw.evaluate(() => chrome.storage.local.remove('assist_cache'));
      const p = await open(url('luma.com', '/personalagenthack'));
      await p.fill(city, 'San Jose');
      const u = await waitFor(async () => { const x = await ui(p); return x && x.chips.length && x; });
      assert.match(u.chips[0].text, /<img src=x/);
      assert.equal(await p.evaluate(() => window.__pwned || 0), 0);
      assert.equal(await p.evaluate(() => document.getElementById('proofloop-observer-host').shadowRoot.querySelectorAll('img,b').length), 0);
      await p.close();
    });

    await step('backend auth from outside the browser', async () => {
      const u = `http://127.0.0.1:${PORT}`;
      assert.equal((await fetch(`${u}/skill`)).status, 403);
      assert.equal((await fetch(`${u}/skill`, { headers: { Authorization: 'Bearer wrong' } })).status, 403);
      assert.equal((await fetch(`${u}/skill`, { headers: { Authorization: `Bearer ${TOKEN}` } })).status, 200);
    });
    console.log(`e2e passed: ${results.length} steps.`);
  } catch (e) {
    console.error(e);
    console.error('backend stderr:', backend.errText && backend.errText().slice(-2000));
    process.exitCode = 1;
  } finally {
    await ctx.close();
    fixtures.close();
    backend.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
})();
