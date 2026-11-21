// Background worker contracts, run in a vm with a fake chrome API. No browser, no network.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const src = fs.readFileSync(path.resolve(__dirname, '../../extension/background.js'), 'utf8');

function load({ granted = [], local = {} } = {}) {
  const store = { token: 'tok', ...local }, session = {}, registered = [], requests = [], executed = [];
  let listener;
  const chrome = {
    storage: {
      local: { get: async (d) => (typeof d === 'string' ? { [d]: store[d] } : Object.fromEntries(Object.entries(d).map(([k, v]) => [k, k in store ? store[k] : v]))), set: async (o) => Object.assign(store, o) },
      session: { get: async (k) => ({ [k]: session[k] }), set: async (o) => Object.assign(session, o) },
    },
    permissions: { contains: async ({ origins }) => origins.every((o) => granted.includes(o)), remove: async () => true, onRemoved: { addListener() {} } },
    scripting: {
      getRegisteredContentScripts: async (f) => registered.filter((r) => !f || f.ids.includes(r.id)),
      registerContentScripts: async (list) => { registered.push(...list); },
      unregisterContentScripts: async ({ ids }) => { for (const id of ids) registered.splice(registered.findIndex((r) => r.id === id), 1); },
      executeScript: async (o) => { executed.push(o); },
    },
    tabs: { onRemoved: { addListener() {} } },
    runtime: { onMessage: { addListener: (fn) => { listener = fn; } }, onInstalled: { addListener() {} }, onStartup: { addListener() {} } },
  };
  const fetch = async (url, init = {}) => { requests.push({ url, init }); return { ok: true, status: 200, json: async () => ({ page_rules: [], context: [] }) }; };
  const ctx = { chrome, fetch, URL, console };
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  const call = (msg, sender) => new Promise((resolve) => { const r = listener(msg, sender, resolve); if (r !== true) resolve(undefined); });
  return { call, store, session, registered, requests, executed };
}
const J = (x) => JSON.parse(JSON.stringify(x));
const page = (url, id = 1) => ({ tab: { id, url, title: 'Private Title' } });

(async () => {
  // /assist gets origin, task and the recall flag only.
  let b = load();
  await b.call({ type: 'assist', task: 'event_registration', title: 'X', value: 'Y' }, page('https://luma.com/personalagenthack?token=abc#f'));
  const req = b.requests[0];
  assert.equal(req.url, 'http://127.0.0.1:8787/assist');
  assert.deepEqual(JSON.parse(req.init.body), { origin: 'https://luma.com', task: 'event_registration', recall: false });
  assert.equal(req.init.headers.Authorization, 'Bearer tok');

  // Messages from non-web pages and popup-only messages from pages are ignored.
  assert.equal(await b.call({ type: 'assist', task: 'x' }, page('chrome://settings')), undefined);
  assert.equal(await b.call({ type: 'watch', origin: 'https://evil.example' }, page('https://evil.example')), undefined);

  // Watching needs the host permission first; then one registration for that origin only.
  b = load();
  assert.equal((await b.call({ type: 'watch', origin: 'https://luma.com', tabId: 3 }, {})).ok, false);
  b = load({ granted: ['https://luma.com/*'] });
  assert.equal((await b.call({ type: 'watch', origin: 'https://luma.com', tabId: 3 }, {})).ok, true);
  assert.deepEqual(J(b.registered.map((r) => r.matches)), [['https://luma.com/*']]);
  assert.deepEqual(J(b.store.watched), ['https://luma.com']);
  assert.equal(b.executed[0].target.tabId, 3);
  await b.call({ type: 'unwatch', origin: 'https://luma.com' }, {});
  assert.equal(b.registered.length, 0);

  // Cross-tab comparison is off by default and stores nothing.
  b = load();
  assert.equal((await b.call({ type: 'observe', task: 'job_application', fields: [{ semantic: 'phone', hash: 'h1', tail: '0100' }] }, page('https://a.example'))).conflicts.length, 0);
  assert.equal(Object.keys(b.session).length, 0);
  // When on: a different hash for the same field in a profile tab is a conflict; only the last 4 characters of the tail are kept.
  b = load({ local: { cross_tab: true } });
  await b.call({ type: 'observe', task: 'profile_edit', fields: [{ semantic: 'phone', hash: 'h-pro', tail: '5550100' }] }, page('https://profile.example', 7));
  const r = await b.call({ type: 'observe', task: 'job_application', fields: [{ semantic: 'phone', hash: 'h-fam', tail: '0199' }] }, page('https://jobs.example', 8));
  assert.equal(r.conflicts.length, 1);
  assert.equal(r.conflicts[0].other_tail, '0100');
  assert.equal(JSON.stringify(b.session).includes('5550100'), false);
  const same = await b.call({ type: 'observe', task: 'job_application', fields: [{ semantic: 'phone', hash: 'h-pro', tail: '0100' }] }, page('https://jobs.example', 8));
  assert.equal(same.conflicts.length, 0);

  // No other backend paths are reachable from pages.
  assert.ok(load().requests.every((q) => q.url.startsWith('http://127.0.0.1:8787/')));
  console.log('background contracts passed: minimal /assist body, page vs popup messages, permission-gated watching, cross-tab off by default and hash-only.');
})().catch((e) => { console.error(e); process.exit(1); });
