// Offline tests for the extension's detector, matcher, task classifier and source rules. jsdom only, no browser.
// Hash parity with harness/page_assist.py is checked against hashes Python computes in this test run.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { JSDOM } = require('jsdom');
const ext = path.resolve(__dirname, '../../extension');
const harness = path.resolve(__dirname, '..');
const D = require(path.join(ext, 'assist/detect.js'));
const M = require(path.join(ext, 'assist/match.js'));
const T = require(path.join(ext, 'assist/task.js'));
const vocab = JSON.parse(fs.readFileSync(path.resolve(harness, '../schemas/tasks.json'), 'utf8'));
const fixture = (n) => new JSDOM(fs.readFileSync(path.join(ext, 'test/fixtures', n), 'utf8'), { url: n.startsWith('luma') ? 'https://luma.com/personalagenthack' : 'https://apply.vouch.us/' }).window.document;
const doc = (html, url = 'https://example.test/') => new JSDOM(`<body>${html}</body>`, { url }).window.document;
const one = (html) => D.classify(doc(html).querySelector('input,select,textarea'));
const pyHash = (field, value) => execFileSync('python3', ['-c', 'import sys,page_assist;print(page_assist.value_hash(sys.argv[1],sys.argv[2]))', field, value], { cwd: harness, env: process.env }).toString().trim();

(async () => {
  // --- detector on the live-captured pages
  const luma = D.collect(fixture('luma_registration.html'));
  const sem = (fs_) => fs_.map((f) => f.semantic);
  assert.deepEqual(sem(luma), ['text', 'email', 'choice', 'text', 'text', 'email', 'city', 'text', 'checkbox', 'checkbox']);
  assert.match(luma[6].label, /^What city are you based in\?/);
  assert.match(luma[9].label, /third-party event sponsors/);
  assert.ok(D.submitControls(fixture('luma_registration.html')).some((s) => s.text === 'Request to Join'));
  const vouch = D.collect(fixture('vouch_apply.html'));
  assert.deepEqual(sem(vouch).filter((s) => s !== 'text'), ['checkbox', 'address', 'choice', 'choice', 'email', 'phone', 'choice', 'checkbox']);
  assert.deepEqual(D.submitControls(fixture('vouch_apply.html')).map((s) => s.text), ['Start Application']);

  // --- detector, synthetic
  for (const [html, want] of [['<input autocomplete="address-level2">', 'city'], ['<label>City <input></label>', 'city'], ['<input name="billing.city">', 'city'],
    ['<label>Street address <input></label>', 'address'], ['<input type="tel">', 'phone'], ['<label>Mobile number <input></label>', 'phone'],
    ['<input type="email">', 'email'], ['<label>Work email <input></label>', 'email'], ['<label>Notes <textarea></textarea></label>', 'text'],
    ['<label>Work type <select><option>Full-time</option></select></label>', 'choice'], ['<label><input type="checkbox"> Share my info with sponsors</label>', 'checkbox'],
    ['<fieldset><legend>Work type</legend><label><input type="radio" name=w> Full-time</label></fieldset>', 'radio']]) assert.equal(one(html).semantic, want, html);
  for (const html of ['<input type="password" aria-label="City">', '<input type="hidden" name="city">', '<input type="checkbox">', '<input>', '<label>Headphones brand <input type="number"></label>'])
    assert.equal(one(html), null, html);
  assert.equal(one('<label>Headphones brand <input></label>').semantic, 'text', '"headphones" is not a phone label');
  assert.deepEqual(D.submitControls(doc('<form><input name=a><button>Send it</button></form>')).map((s) => s.text), ['Send it']);
  assert.deepEqual(D.submitControls(doc('<div><button type="button">Apply filters</button></div>')), []);

  // --- hash parity with Python, then matcher behavior
  for (const [field, value] of [['city', 'San José'], ['phone', '+1 (415) 555-0100'], ['email', 'A.B@Example.com'], ['city', 'São Paulo']]) {
    assert.equal(await M.sha256Hex(`${M.SALT}${field}:${M.normalize(field, value)}`), pyHash(field, value), `hash parity ${field} ${value}`);
  }
  for (const t of ['', 'abc', 'x'.repeat(55), 'x'.repeat(64), 'é漢字🙂'.repeat(9)]) {
    const want = require('node:crypto').createHash('sha256').update(t).digest('hex');
    assert.equal(M.sha256Sync(new TextEncoder().encode(t)), want, `fallback sha256 length ${t.length}`);
  }
  const city = { id: 'c', kind: 'forbid_value', field: 'city', message: 'm', forbid: [{ sha256: pyHash('city', 'San Jose'), label: 'San Jose' }], expect_label: 'San Francisco' };
  const phone = { id: 'p', kind: 'forbid_value', field: 'phone', message: 'm', forbid: [{ sha256: pyHash('phone', '415 555 0100'), label: '[PHONE-FAMILY]' }] };
  const hit = async (rule, semantic, value) => !!(await M.evaluate(rule, { semantic, label: '', value }));
  for (const v of ['San Jose', 'san josé', 'SAN JOSE', 'San Jose, CA', 'San Jose CA', '  San   Jose ']) assert.ok(await hit(city, 'city', v), v);
  for (const v of ['', 'San Francisco', 'San Jose Street', 'North San Jose', 'San Jose del Cabo', 'SJC']) assert.ok(!(await hit(city, 'city', v)), v);
  for (const v of ['123 Main St, San Jose, CA 95112', '123 Main St, San Jose', '123 Main St San Jose CA 95112', '1 South Main Street, San Jose, CA',
    'S Main St San Jose, US-CA 95035' /* the value live Vouch writes after a suggestion is picked */]) assert.ok(await hit(city, 'address', v), v);
  for (const v of ['123 San Jose Ave, San Francisco, CA 94110', '1 San Jose Ave', '500 Main, Oakland, CA', '1 Market St San Francisco, US-CA 94105', '9 San Jose Ave, Oakland, US-CA 94601']) assert.ok(!(await hit(city, 'address', v)), v);
  assert.ok(!(await hit(city, 'text', 'San Jose')), 'city rule ignores a company field');
  for (const v of ['415-555-0100', '(415) 555 0100', '+1 415 555 0100']) assert.ok(await hit(phone, 'phone', v), v);
  for (const v of ['415-555-0101', '555-0100', '415 555 0100 ext 2']) assert.ok(!(await hit(phone, 'phone', v)), v);
  assert.ok(!(await hit({ ...phone, forbid: [{ sha256: null, label: '[PHONE-FAMILY]' }] }, 'phone', '415-555-0100')), 'unresolved placeholder never matches');
  const consent = { id: 'k', kind: 'keep_unchecked', message: 'm', terms: ['third-party', 'sponsors'] };
  assert.ok(await M.evaluate(consent, { semantic: 'checkbox', label: luma[9].label, checked: true }));
  assert.equal(await M.evaluate(consent, { semantic: 'checkbox', label: luma[9].label, checked: false }), null);
  assert.equal(await M.evaluate(consent, { semantic: 'checkbox', label: vouch[7].label, checked: true }), null, 'Vouch terms box ("Communications Consent") is not the sponsor box');
  const confirm = { id: 'w', kind: 'confirm_choice', message: 'm', terms: ['work type'] };
  assert.equal((await M.evaluate(confirm, { semantic: 'choice', label: 'Work type', value: 'Full-time' })).atSubmit, true);
  assert.equal(await M.evaluate(confirm, { semantic: 'choice', label: 'Work type', value: '' }), null);

  // --- task classification (no hostnames involved)
  const lumaDoc = fixture('luma_registration.html');
  assert.equal(T.classify(vocab, lumaDoc, D.collect(lumaDoc)).task, 'event_registration');
  const vouchDoc = fixture('vouch_apply.html');
  assert.equal(T.classify(vocab, vouchDoc, D.collect(vouchDoc)).task, 'insurance_or_service_quote');
  const job = doc('<h1>Apply for Senior Engineer</h1><form><label>Phone <input type=tel></label><label>LinkedIn <input></label><button>Submit application</button></form>', 'https://jobs.example.test/apply');
  assert.equal(T.classify(vocab, job, D.collect(job)).task, 'job_application');
  const blog = doc('<h1>My trip</h1><p>We applied sunscreen</p>');
  assert.equal(T.classify(vocab, blog, D.collect(blog)).task, 'other', 'no form, no task');

  // --- source rules (security S1): no HTML-string sinks, closed shadow root, no static host access
  const files = ['background.js', 'options.js', 'popup.js', 'assist/detect.js', 'assist/match.js', 'assist/task.js', 'assist/observer.js'];
  for (const f of files) assert.doesNotMatch(fs.readFileSync(path.join(ext, f), 'utf8'), /\binnerHTML\b|\bouterHTML\b|insertAdjacentHTML|document\.write\b|\beval\(|new Function\(/, f);
  const obs = fs.readFileSync(path.join(ext, 'assist/observer.js'), 'utf8');
  assert.match(obs, /attachShadow\(\{ mode: "closed" \}\)/);
  assert.doesNotMatch(obs, /\.value\s*=[^=]|\.checked\s*=[^=]|dispatchEvent|\.focus\(\)/, 'observer never writes to page fields');
  const mf = JSON.parse(fs.readFileSync(path.join(ext, 'manifest.json'), 'utf8'));
  assert.equal(mf.content_scripts, undefined, 'no static content scripts: only sites Ari turns on');
  assert.deepEqual(mf.host_permissions, ['http://127.0.0.1:8787/*', 'http://localhost:8787/*']);
  // Exact list. No "tabs": host permissions (per-site grants, or the optional all-hosts grant for "Watch all
  // tabs") already expose url/title for the tabs ProofLoop may read; "tabs" would expose every other tab too.
  assert.deepEqual(mf.permissions, ['storage', 'scripting', 'activeTab']);
  console.log('extension offline tests passed: detector on live captures, hash parity with Python, matcher incl. near misses, task classifier, source rules.');
})().catch((e) => { console.error(e); process.exit(1); });
