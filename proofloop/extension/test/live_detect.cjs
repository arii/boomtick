// Milestone 2 live check: run the shipped detector on the live Luma dialog and the live Vouch Apply form.
// Read-only: opens the pages, clicks "Request to Join" on Luma to mount the dialog, types nothing, submits nothing.
//   NODE_PATH=... node proofloop/extension/test/live_detect.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { chromium } = (() => { try { return require('@playwright/test'); } catch { return require('playwright'); } })();
const src = fs.readFileSync(path.resolve(__dirname, '../assist/detect.js'), 'utf8');
const tmp = fs.mkdtempSync(path.join(process.env.PROOFLOOP_E2E_TMP || os.tmpdir(), 'proofloop-detect-'));

const report = (page) => page.evaluate((code) => {
  (0, eval)(code);
  const D = globalThis.ProofLoopDetect;
  const all = [...document.querySelectorAll('input')];
  const fields = D.collect(document).map((f) => ({ id: f.el.id || null, semantic: f.semantic, label: f.label.slice(0, 200) }));
  const undetected = all.filter((el) => !D.classify(el)).map((el) => ({ id: el.id || null, type: el.type, label: (D.labelText(el) || el.placeholder || '').slice(0, 50) }));
  const submits = D.submitControls(document).map((s) => s.text);
  return { inputs: all.length, fields, undetected, submits };
}, src);

(async () => {
  const b = await chromium.launch({ channel: 'chromium', headless: true, env: { ...process.env, HOME: tmp } });
  try {
    const page = await b.newPage();
    await page.goto('https://luma.com/personalagenthack', { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'Request to Join' }).click();
    await page.getByLabel(/What city are you based in/).waitFor({ timeout: 15000 });
    const luma = await report(page);
    console.log('LUMA', JSON.stringify(luma, null, 1));
    assert.deepEqual(luma.fields.filter((f) => f.semantic !== 'checkbox').map((f) => f.semantic), ['city']);
    const cb = luma.fields.filter((f) => f.semantic === 'checkbox').map((f) => f.label);
    assert.equal(cb.length, 2);
    assert.match(cb[0], /^Judge applicants/);
    assert.match(cb[1], /consent to providing your contact information to third-party event sponsors/);
    assert.ok(luma.submits.includes('Request to Join'), 'Luma submit control found');

    await page.goto('https://apply.vouch.us/', { waitUntil: 'domcontentloaded' });
    await page.getByLabel('Phone Number').waitFor({ timeout: 15000 });
    const vouch = await report(page);
    console.log('VOUCH', JSON.stringify(vouch, null, 1));
    assert.deepEqual(vouch.fields.filter((f) => f.semantic !== 'checkbox').map((f) => f.semantic).sort(), ['address', 'phone']);
    assert.equal(vouch.fields.filter((f) => f.semantic === 'checkbox').length, 2);
    assert.ok(vouch.submits.includes('Start Application'), 'Vouch submit control found');
    console.log('live detector passed on Luma and Vouch');
  } finally {
    await b.close();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
})().catch((e) => { console.error(e.message || e); process.exit(1); });
