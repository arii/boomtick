// End-to-end: real Chromium with the unpacked extension, the real backend, and page fixtures.
//   NODE_PATH=<dir with playwright> PYTHONPATH=<dir with jsonschema> node proofloop/extension/test/e2e_assist.cjs
// Test-only changes to a COPY of the extension: the manifest gets the test hosts and a fixed key (so the extension
// ID is known), and the chip's closed shadow root is opened so Playwright can read it. The shipped files are untouched.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
// The repo pins @playwright/test; a standalone playwright install also works.
const { chromium } = (() => { try { return require('@playwright/test'); } catch { return require('playwright'); } })();

const root = path.resolve(__dirname, '../..');
const TOKEN = 'e2e-token-' + crypto.randomBytes(8).toString('hex');
const BACKEND_PORT = 8787;
const tmp = fs.mkdtempSync(path.join(process.env.PROOFLOOP_E2E_TMP || os.tmpdir(), 'proofloop-e2e-'));

function prepareExtension() {
  const dir = path.join(tmp, 'ext');
  fs.cpSync(path.join(root, 'extension'), dir, { recursive: true, filter: (s) => !s.includes('/test/') });
  const { publicKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
  const der = publicKey.export({ type: 'spki', format: 'der' });
  const id = [...crypto.createHash('sha256').update(der).digest().subarray(0, 16)].map((b) => String.fromCharCode(97 + (b >> 4)) + String.fromCharCode(97 + (b & 15))).join('');
  const mf = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json'), 'utf8'));
  mf.key = der.toString('base64');
  mf.content_scripts[0].matches.push('http://luma.com/*', 'http://example.com/*');
  fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify(mf));
  const a = path.join(dir, 'assist/assist.js');
  fs.writeFileSync(a, fs.readFileSync(a, 'utf8').replace('attachShadow({ mode: "closed" })', 'attachShadow({ mode: "open" })'));
  return { dir, id };
}

function startFixtures() {
  const fx = path.join(root, 'extension/test/fixtures');
  const srv = http.createServer((req, res) => {
    const f = req.url.startsWith('/vouch') ? 'vouch_apply.html' : 'luma_registration.html';
    // Stand-in for a React form: records what the page's own scripts see, so we can check that the fix reaches page state.
    const probe = '<script>window.__seen=[];document.addEventListener("input",e=>window.__seen.push(e.target.value),true)</script>';
    res.setHeader('Content-Type', 'text/html');
    res.end(fs.readFileSync(path.join(fx, f), 'utf8') + probe);
  });
  return new Promise((r) => srv.listen(0, '127.0.0.1', () => r(srv)));
}

function startBackend(extId, cards) {
  const state = path.join(tmp, 'state');
  fs.mkdirSync(state, { recursive: true });
  const p = spawn('python3', [path.join(root, 'harness/server.py'), String(BACKEND_PORT)], {
    env: { ...process.env, PROOFLOOP_EXTENSION_ID: extId, PROOFLOOP_TOKEN: TOKEN, PROOFLOOP_STATE: state, PROOFLOOP_CARDS: cards },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let err = '';
  p.stderr.on('data', (d) => (err += d));
  return { p, state, err: () => err };
}

async function waitFor(fn, ms = 6000) {
  const end = Date.now() + ms;
  for (;;) { const v = await fn(); if (v) return v; if (Date.now() > end) throw new Error('timeout'); await new Promise((r) => setTimeout(r, 100)); }
}

const chipText = (page) => page.evaluate(() => { const h = document.getElementById('proofloop-assist-host'); const c = h && h.shadowRoot && h.shadowRoot.querySelector('.chip'); return c && h.style.display !== 'none' ? c.innerText : null; });
const clickChip = (page, name) => page.evaluate((n) => [...document.getElementById('proofloop-assist-host').shadowRoot.querySelectorAll('button')].find((b) => b.textContent.startsWith(n)).click(), name);

(async () => {
  const { dir, id } = prepareExtension();
  const v1 = path.join(tmp, 'cards_v1.json');
  fs.writeFileSync(v1, JSON.stringify({ version: 1, cards: [] }));
  // v2 = the shipped card file, renumbered so the version change is visible on the page.
  const v2 = path.join(tmp, 'cards_v2.json');
  fs.writeFileSync(v2, JSON.stringify({ ...JSON.parse(fs.readFileSync(path.join(root, 'data/cards.json'), 'utf8')), version: 2 }));
  let backend = startBackend(id, v1);
  await waitFor(async () => { try { return (await fetch(`http://127.0.0.1:${BACKEND_PORT}/`)).ok; } catch { return false; } });
  const fixtures = await startFixtures();
  const fport = fixtures.address().port;
  const ctx = await chromium.launchPersistentContext(path.join(tmp, 'profile'), {
    channel: 'chromium', headless: true,
    // Chrome needs a writable HOME; some sandboxes mount it read-only.
    env: { ...process.env, HOME: tmp },
    args: [`--disable-extensions-except=${dir}`, `--load-extension=${dir}`, '--host-resolver-rules=MAP luma.com 127.0.0.1, MAP example.com 127.0.0.1'],
  });
  try {
    const sw = ctx.serviceWorkers()[0] || await ctx.waitForEvent('serviceworker');
    assert.equal(new URL(sw.url()).host, id, 'extension id matches the test key');
    await sw.evaluate((t) => chrome.storage.local.set({ token: t }), TOKEN);
    const city = '#_r_n_', company = '#_r_k_';
    const lumaUrl = `http://luma.com:${fport}/personalagenthack`;
    const open = async (url) => { const p = await ctx.newPage(); await p.goto(url); await p.waitForTimeout(600); return p; };

    // 1. Rule set v1 has no city rule: typing San Jose shows nothing.
    let page = await open(lumaUrl);
    await page.fill(city, 'San Jose');
    await page.waitForTimeout(700);
    assert.equal(await chipText(page), null, 'no chip while the active rule set has no city rule');
    await page.close();

    // 2. Promote v2 (swap the card file the backend reads), reload: same typing now warns, citing the rule and version.
    backend.p.kill(); await new Promise((r) => backend.p.once('exit', r));
    backend = startBackend(id, v2);
    await waitFor(async () => { try { return (await fetch(`http://127.0.0.1:${BACKEND_PORT}/`)).ok; } catch { return false; } });
    page = await open(lumaUrl);
    await page.fill(city, 'San Jose');
    const text = await waitFor(() => chipText(page));
    assert.match(text, /San Francisco here, not San Jose/);
    assert.match(text, /rule\.city\.sf/);
    assert.match(text, /set v2/);
    assert.match(text, /vouch 11\/16/);
    console.log('chip text:', JSON.stringify(text));

    // 3. Negative cases: other field types, a correct city, an empty value.
    await page.fill(city, '');
    await page.waitForTimeout(700);
    assert.equal(await chipText(page), null, 'clearing the field removes the chip');
    await page.fill(company, 'San Jose');
    await page.waitForTimeout(700);
    assert.equal(await chipText(page), null, 'company field with the same text does not warn');
    await page.fill(city, 'San Francisco');
    await page.waitForTimeout(700);
    assert.equal(await chipText(page), null, 'a correct city does not warn');

    // 4. Use the fix: value changes and the page's own listeners saw it.
    await page.fill(city, 'San Jose, CA');
    await waitFor(() => chipText(page));
    await clickChip(page, 'Use San Francisco');
    assert.equal(await page.inputValue(city), 'San Francisco, CA');
    assert.equal((await page.evaluate(() => window.__seen)).pop(), 'San Francisco, CA', 'page listeners observed the fix');
    assert.equal(await chipText(page), null);

    // 5. Keep: the chip goes away and does not come back for the same value, but comes back for a different bad value.
    await page.fill(city, 'San Jose');
    await waitFor(() => chipText(page));
    await clickChip(page, 'Keep');
    assert.equal(await page.inputValue(city), 'San Jose', 'Keep leaves the value alone');
    await page.focus(company); await page.focus(city); await page.waitForTimeout(500);
    assert.equal(await chipText(page), null, 'dismissed value stays dismissed');
    await page.fill(city, 'SJ');
    await waitFor(() => chipText(page));

    // 6. Feedback was recorded, with ids and actions only.
    const lines = await waitFor(() => { try { const l = fs.readFileSync(path.join(backend.state, 'feedback.jsonl'), 'utf8').trim().split('\n'); return l.length >= 4 && l; } catch { return false; } });
    const acts = lines.map((l) => JSON.parse(l)).map((r) => r.action);
    assert.ok(acts.includes('used_suggestion') && acts.includes('kept_value') && acts.includes('shown'), acts.join());
    assert.ok(!/San Jose|SJ/.test(lines.join('')), 'feedback carries no field values');
    await page.close();

    // 7. Out-of-scope host (example.com is not in any card scope), same form markup: no chip.
    page = await open(`http://example.com:${fport}/x?secret=1#frag`);
    await page.fill(city, 'San Jose');
    await page.waitForTimeout(700);
    assert.equal(await chipText(page), null, 'out-of-scope host does not warn');
    await page.close();

    // 8. Backend unreachable with a cached rule set: the matcher keeps working from cache.
    backend.p.kill(); await new Promise((r) => backend.p.once('exit', r));
    page = await open(lumaUrl);
    await page.fill(city, 'San Jose');
    const cached = await waitFor(() => chipText(page));
    assert.match(cached, /\(cached\)/);
    await page.close();

    // 9. Page-injected markup never becomes DOM in the chip (text only).
    const evilCards = path.join(tmp, 'evil.json');
    const evil = JSON.parse(fs.readFileSync(v2, 'utf8'));
    evil.cards[0].message = '<img src=x onerror="window.__pwned=1"><b>x</b>';
    fs.writeFileSync(evilCards, JSON.stringify(evil));
    backend = startBackend(id, evilCards);
    await waitFor(async () => { try { return (await fetch(`http://127.0.0.1:${BACKEND_PORT}/`)).ok; } catch { return false; } });
    await sw.evaluate(() => chrome.storage.local.remove('cards_cache'));
    page = await open(lumaUrl);
    await page.fill(city, 'San Jose');
    const evilText = await waitFor(() => chipText(page));
    assert.match(evilText, /<img src=x/);
    assert.equal(await page.evaluate(() => window.__pwned || 0), 0);
    assert.equal(await page.evaluate(() => document.getElementById('proofloop-assist-host').shadowRoot.querySelectorAll('img,b').length), 0);
    await page.close();

    // 10. Auth, from outside the browser.
    const u = `http://127.0.0.1:${BACKEND_PORT}`;
    assert.equal((await fetch(`${u}/skill`)).status, 403);
    assert.equal((await fetch(`${u}/skill`, { headers: { Authorization: 'Bearer wrong' } })).status, 403);
    assert.equal((await fetch(`${u}/skill`, { headers: { Authorization: `Bearer ${TOKEN}` } })).status, 200);

    console.log('e2e passed: version change v1 -> v2, chip text and citation, negatives, use/keep, feedback, scope, cache fallback, text-only rendering, auth.');
  } finally {
    await ctx.close();
    fixtures.close();
    backend.p.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
})().catch((e) => { console.error(e); process.exit(1); });
