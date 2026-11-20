// Offline tests for the field detector, the matcher and extension source rules. jsdom only, no browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const ext = path.resolve(__dirname, '../../extension');
const { classify, collect } = require(path.join(ext, 'assist/detect.js'));
const { evaluate } = require(path.join(ext, 'assist/match.js'));
const fixture = (n) => new JSDOM(fs.readFileSync(path.join(ext, 'test/fixtures', n), 'utf8')).window.document;

// --- detector on the captured pages
const luma = collect(fixture('luma_registration.html'));
assert.deepEqual(luma.map((f) => [f.el.id, f.semantic]), [['_r_n_', 'city']], 'Luma: only the city question is a city field');
assert.match(luma[0].label, /^What city are you based in\?/);
assert.equal(luma[0].el.getAttribute('autocomplete'), '', 'Luma city field has no autocomplete, so the label is the only signal');

const vouch = collect(fixture('vouch_apply.html'));
assert.deepEqual(vouch.map((f) => [f.el.id, f.semantic]), [[':r3:', 'address']], 'Vouch Apply: the placeholder-only address combobox is an address, not a city');

// --- detector on synthetic markup
const doc = (html) => new JSDOM(`<body>${html}</body>`).window.document;
const one = (html) => classify(doc(html).querySelector('input'));
assert.equal(one('<input autocomplete="address-level2">').semantic, 'city');
assert.equal(one('<label>City <input></label>').semantic, 'city');
assert.equal(one('<input name="billing.city">').semantic, 'city');
assert.equal(one('<input aria-label="Town or city">').semantic, 'city');
assert.equal(one('<input placeholder="City">').semantic, 'city');
assert.equal(one('<span id=l>Where are you based?</span><input aria-labelledby=l>').semantic, 'city');
assert.equal(one('<label>Street address <input></label>').semantic, 'address');
assert.equal(one('<input autocomplete="street-address">').semantic, 'address');
for (const html of ['<label>Capacity <input></label>', '<label>Velocity <input></label>', '<label>Email address <input></label>',
  '<label>Company <input></label>', '<input type="password" aria-label="City">', '<input type="checkbox" aria-label="City">',
  '<input type="email" aria-label="City">', '<textarea aria-label="City"></textarea>', '<input placeholder="Search the city archive">']) {
  const d = doc(html), n = d.querySelector('input,textarea');
  assert.equal(classify(n), null, html);
}

// --- matcher
const card = { id: 'rule.city.sf', kind: 'forbid_value', field: { semantic: 'city' }, forbid: ['san jose', 'sj'], expect: 'San Francisco', message: 'm' };
const addr = { ...card, field: { semantic: 'address' } };
const fix = (c, s, v) => { const h = evaluate(c, s, v); return h && h.replacement; };
for (const [v, want] of [['San Jose', 'San Francisco'], ['san josé', 'San Francisco'], ['SAN JOSE', 'San Francisco'], ['San Jose, CA', 'San Francisco, CA'],
  ['San Jose CA', 'San Francisco CA'], ['SJ', 'San Francisco'], ['sj.', 'San Francisco'], ['  San   Jose ', 'San Francisco']]) assert.equal(fix(card, 'city', v), want, v);
for (const v of ['', ' ', 'San Francisco', 'San Francisco, CA', 'San Jose Street', 'North San Jose', 'San Jose del Cabo', 'Santa Clara', 'SJC', 'sj airport', 'S']) assert.equal(evaluate(card, 'city', v), null, `no warning: ${JSON.stringify(v)}`);
for (const [v, want] of [['123 Main St, San Jose, CA 95112', '123 Main St, San Francisco, CA 95112'], ['123 Main St, San Jose', '123 Main St, San Francisco'],
  ['123 Main St San Jose CA 95112', '123 Main St San Francisco CA 95112'], ['12 Main, San José, California, USA', '12 Main, San Francisco, California, USA'], ['San Jose, CA', 'San Francisco, CA']]) assert.equal(fix(addr, 'address', v), want, v);
for (const v of ['123 San Jose Ave, San Francisco, CA 94110', '1 San Jose Ave', '500 SJ Blvd, Oakland, CA', '123 Main St, San Francisco, CA 94110', '55 Main St, Suite 4']) assert.equal(evaluate(addr, 'address', v), null, `no warning: ${v}`);
assert.equal(evaluate(card, 'address', 'San Jose'), null, 'a city card does not fire on an address field');
assert.equal(evaluate({ ...card, kind: 'run_code' }, 'city', 'San Jose'), null, 'unknown card kinds are ignored');

// --- source rules (security plan S1): no HTML-string sinks, chip shadow root closed in the shipped file
const sources = ['background.js', 'content.js', 'options.js', 'assist/detect.js', 'assist/match.js', 'assist/assist.js'].map((f) => [f, fs.readFileSync(path.join(ext, f), 'utf8')]);
for (const [f, src] of sources) assert.doesNotMatch(src, /\binnerHTML\b|\bouterHTML\b|insertAdjacentHTML|document\.write\b|\beval\(|new Function\(/, `${f} uses an HTML or code string sink`);
assert.match(fs.readFileSync(path.join(ext, 'assist/assist.js'), 'utf8'), /attachShadow\(\{ mode: "closed" \}\)/);
const manifest = JSON.parse(fs.readFileSync(path.join(ext, 'manifest.json'), 'utf8'));
for (const cs of manifest.content_scripts) for (const m of cs.matches) assert.doesNotMatch(m, /^(https?|\*):\/\/\*\/|<all_urls>/, `manifest match too broad: ${m}`);

console.log('assist offline tests passed: detector on Luma and Vouch captures, ambiguous labels, matcher cases, source sink rules, narrow manifest.');
