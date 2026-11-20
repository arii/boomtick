// Offline service-worker contract tests, no Chrome session or fetch to a network.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../extension');

(async () => {
  let listener, requested = [], optIn = false, tabReads = 0;
  const context = {
    chrome: {
      storage: { local: { get: async () => ({ local_related_tabs: optIn }) } },
      tabs: { query: async () => { tabReads++; return [{ id: 2, title: 'LOCAL ONLY', url: 'https://private.invalid' }]; } },
      runtime: { onMessage: { addListener: fn => { listener = fn; } } },
    },
    fetch: async url => { requested.push(url); return { ok: true, json: async () => ({ active_version: 'v1' }) }; },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(root, 'background.js'), 'utf8'), context);
  const invoke = () => new Promise(resolve => listener({ type: 'augment', title: 'PRIVATE TITLE', url: 'https://private.invalid', snippet: 'PRIVATE BODY' }, { tab: { id: 1, windowId: 1 } }, resolve));
  const first = await invoke();
  assert.equal(tabReads, 0);
  assert.equal(first.related.length, 0);
  assert.deepEqual(requested, ['http://127.0.0.1:8787/augment']);
  optIn = true;
  const second = await invoke();
  assert.equal(tabReads, 1);
  assert.equal(second.related[0].title, 'LOCAL ONLY');
  assert.deepEqual(requested, ['http://127.0.0.1:8787/augment', 'http://127.0.0.1:8787/augment']);
  const content = fs.readFileSync(path.join(root, 'content.js'), 'utf8');
  for (const forbidden of ['document.title', 'location.href', 'innerText', 'LanguageModel', 'snippet:']) assert(!content.includes(forbidden), forbidden);
  const options = fs.readFileSync(path.join(root, 'options.js'), 'utf8');
  assert(!/API_KEY|\/config|backend_url/.test(options));
  assert(!content.includes(' verified'));
  console.log('7 offline extension contracts passed: fixed status URL, no metadata/body upload, tab lookup opt-in, local-only tab results, no key form/config writes, no verified claim, no local model invocation.');
})();
