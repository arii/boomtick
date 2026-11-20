// Re-capture the Luma and Vouch form fixtures from the live pages. Keeps form structure (tags, ids, names, labels,
// roles, aria, types, placeholders, autocomplete); drops scripts, styles, images, inline styles, data-* attributes
// and long class lists. Nothing is typed or submitted.
//   NODE_PATH=... node proofloop/extension/test/capture_fixtures.cjs
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { chromium } = (() => { try { return require('@playwright/test'); } catch { return require('playwright'); } })();
const out = path.resolve(__dirname, 'fixtures');
const tmp = fs.mkdtempSync(path.join(process.env.PROOFLOOP_E2E_TMP || os.tmpdir(), 'proofloop-cap-'));

const sanitize = (rootSel) => {
  const root = document.querySelector(rootSel);
  const c = root.cloneNode(true);
  c.querySelectorAll('script,style,svg,img,picture,video,link,noscript,iframe').forEach((n) => n.remove());
  for (const n of [c, ...c.querySelectorAll('*')]) for (const a of [...n.attributes]) {
    if (a.name === 'style' || a.name.startsWith('data-') || a.name.startsWith('on')) n.removeAttribute(a.name);
    else if (a.name === 'class') n.setAttribute('class', a.value.split(/\s+/).slice(0, 2).join(' '));
    else if (a.name === 'href' && !/^https:\/\//.test(a.value)) n.removeAttribute('href');
  }
  return c.outerHTML;
};

const page_ = (title, source, note, body) => `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${title} (fixture)</title></head><body>
<!-- Fixture captured by extension/test/capture_fixtures.cjs from ${source} on ${new Date().toISOString().slice(0, 10)}. ${note}
     Scripts, styles, images, inline styles and data-* attributes removed. Nothing was typed or submitted. -->
${body}
</body></html>
`;

(async () => {
  const b = await chromium.launch({ channel: 'chromium', headless: true, env: { ...process.env, HOME: tmp } });
  try {
    const p = await b.newPage();
    await p.goto('https://luma.com/personalagenthack', { waitUntil: 'domcontentloaded' });
    await p.getByRole('button', { name: 'Request to Join' }).click();
    await p.getByLabel(/What city are you based in/).waitFor({ timeout: 15000 });
    fs.writeFileSync(path.join(out, 'luma_registration.html'), page_('Personal Agents Hackathon · Luma', 'https://luma.com/personalagenthack',
      'Request to Join dialog, no login needed. The city field has no autocomplete and no placeholder; its only signal is the label.',
      await p.evaluate(sanitize, '[role=dialog]')));
    await p.goto('https://apply.vouch.us/', { waitUntil: 'domcontentloaded' });
    await p.getByLabel('Phone Number').waitFor({ timeout: 15000 });
    const root = await p.evaluate(() => { let n = document.querySelector('input'); while (n.parentElement && n.parentElement.querySelectorAll('input').length < document.querySelectorAll('input').length) n = n.parentElement; n.parentElement.setAttribute('data-pl-root', '1'); return true; });
    const html = await p.evaluate(() => { const r = document.querySelector('[data-pl-root]'); r.removeAttribute('data-pl-root'); r.id = r.id || 'pl-root'; return r.id; });
    fs.writeFileSync(path.join(out, 'vouch_apply.html'), page_('Vouch Apply', 'https://apply.vouch.us/',
      'Business insurance application, public. Not confirmed to be the Vouch form from the Nov 16 session. No city field: the address is one combobox with only a placeholder.',
      await p.evaluate(sanitize, '#' + CSS_escape(html))));
    console.log('captured', fs.readdirSync(out).map((f) => `${f} ${fs.statSync(path.join(out, f)).size}B`).join(', '));
  } finally {
    await b.close();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
})().catch((e) => { console.error(e.message || e); process.exit(1); });

function CSS_escape(id) { return id.replace(/[^a-zA-Z0-9_-]/g, (c) => '\\' + c); }
