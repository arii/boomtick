// Background worker contracts, run in a vm with a fake chrome API. No browser, no network.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const src = fs.readFileSync(path.resolve(__dirname, '../../extension/background.js'), 'utf8');

function load({ granted = [], local = {}, openTabs = [] } = {}) {
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
    tabs: { onRemoved: { addListener() {} }, query: async () => openTabs },
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
  // /assist gets origin, task, the recall flag and a compact other-tabs list only.
  let b = load();
  await b.call({ type: 'assist', task: 'event_registration', title: 'X', value: 'Y' }, page('https://luma.com/personalagenthack?token=abc#f'));
  const req = b.requests[0];
  assert.equal(req.url, 'http://127.0.0.1:8787/assist');
  assert.deepEqual(JSON.parse(req.init.body), { origin: 'https://luma.com', task: 'event_registration', recall: false, open_tabs: [] });
  assert.equal(req.init.headers.Authorization, 'Bearer tok');

  // The snapshot follows tabs across calls: the second page's /assist names the first tab (origin + short title).
  await b.call({ type: 'assist', task: 'other' }, page('https://boomtick.blog/ads.txt?x=1', 2));
  assert.deepEqual(JSON.parse(b.requests[1].init.body).open_tabs, [{ origin: 'https://luma.com', title: 'Private Title' }]);
  await b.call({ type: 'assist', task: 'other' }, page('chrome://settings', 3));
  assert.equal(b.requests.length, 2, 'non-web pages never reach the backend');

  // Pause quiets everything without a backend call; unpause resumes.
  await b.call({ type: 'pause' }, {});
  const pr = await b.call({ type: 'assist', task: 'other' }, page('https://luma.com/', 1));
  assert.equal(pr.paused, true);
  assert.equal(b.requests.length, 2);
  await b.call({ type: 'unpause' }, {});
  await b.call({ type: 'assist', task: 'other' }, page('https://luma.com/', 1));
  assert.equal(b.requests.length, 3);

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

  // Watch-all needs the all-hosts grant; then one all-urls registration plus injection into every open tab.
  b = load({ openTabs: [{ id: 1 }, { id: 2 }, {}] });
  assert.equal((await b.call({ type: 'watchAll' }, {})).ok, false);
  assert.equal(b.registered.length, 0);
  b = load({ granted: ['https://*/*', 'http://*/*'], openTabs: [{ id: 1 }, { id: 2 }, {}] });
  assert.equal((await b.call({ type: 'watchAll' }, {})).ok, true);
  assert.deepEqual(J(b.registered.map((r) => r.matches)), [['https://*/*', 'http://*/*']]);
  assert.deepEqual(J(b.executed.map((e) => e.target.tabId)), [1, 2]);
  assert.equal(b.store.watch_all, true);
  assert.equal(b.store.cross_tab, true);
  assert.equal(await b.call({ type: 'watchAll' }, page('https://evil.example')), undefined);
  await b.call({ type: 'unwatchAll' }, {});
  assert.equal(b.registered.length, 0);
  assert.equal(b.store.watch_all, false);

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

  // A configured backend URL is used for requests (normalized to its origin); invalid values fall back to the default.
  b = load({ local: { backend_url: 'https://pl.example.test:9443/ignored/path?x=1' } });
  await b.call({ type: 'assist', task: 'other' }, page('https://luma.com/'));
  assert.equal(b.requests[0].url, 'https://pl.example.test:9443/assist');
  assert.equal(b.requests[0].init.headers.Authorization, 'Bearer tok');
  b = load({ local: { backend_url: 'file:///etc/passwd' } });
  await b.call({ type: 'assist', task: 'other' }, page('https://luma.com/'));
  assert.equal(b.requests[0].url, 'http://127.0.0.1:8787/assist');

  // No other backend paths are reachable from pages (default configuration).
  assert.ok(load().requests.every((q) => q.url.startsWith('http://127.0.0.1:8787/')));
  console.log('background contracts passed: configurable backend URL, minimal /assist body, page vs popup messages, permission-gated watching, watch-all tabs, cross-tab off by default and hash-only.');
})().catch((e) => { console.error(e); process.exit(1); });
