// ProofLoop background worker.
// - Watched sites: content scripts run on origins Ari turns on in the popup, or on every http(s) tab when
//   "Watch all tabs" is on (one optional all-hosts grant). Nothing runs on other sites.
// - Backend calls go only to the configured backend (default loopback) with the per-run token. /assist receives the page origin,
//   the task id, and a compact list of other open tabs (origin + short title, no paths or query strings),
//   never the URL path, query, title, page text or field values.
// - Open-tab snapshot: title, origin, domain and last-active time per tab, in memory only, kept from
//   chrome.tabs events. chrome://, chrome-extension:// and edge:// pages are never recorded.
// - Pause: when paused, pages get no assist data and render nothing until unpaused.
// - Cross-tab facts: hashed field values per tab, kept in chrome.storage.session (memory only, cleared when the
//   browser closes), and only when "compare with my other watched tabs" is on.
const DEFAULT_BACKEND = "http://127.0.0.1:8787";
// The backend URL is the stored `backend_url` (options page), normalized to an http(s) origin; anything else falls back to the default.
function backendOrigin(value) {
  try {
    const u = new URL(String(value || ""));
    return /^https?:$/.test(u.protocol) ? u.origin : DEFAULT_BACKEND;
  } catch { return DEFAULT_BACKEND; }
}
const SCRIPTS = ["assist/detect.js", "assist/match.js", "assist/task.js", "assist/observer.js"];
// Match patterns ignore ports, so they are built from scheme and hostname.
const patternFor = (origin) => { const u = new URL(origin); return `${u.protocol}//${u.hostname}/*`; };
const scriptId = (origin) => "pl-" + origin.replace(/[^a-z0-9]/gi, "_").slice(0, 80);
const ALL_MATCHES = ["https://*/*", "http://*/*"];
const ALL_ID = "pl-all";

async function settings() {
  return chrome.storage.local.get({ token: "", backend_url: DEFAULT_BACKEND, watched: [], watch_all: false, paused: false, hold_submit: true, cross_tab: false, cloud_recall: false });
}

// ---------------------------------------------------------------- open-tab snapshot (memory only)
const TABS = new Map(); // tabId -> { origin, domain, title, task, at }
const WEB_URL = /^https?:\/\//;
function snapTab(tab) {
  if (!tab || tab.id == null || !WEB_URL.test(tab.url || "")) return;
  try {
    const u = new URL(tab.url);
    TABS.set(tab.id, { origin: u.origin, domain: u.hostname, title: (tab.title || "").slice(0, 80), task: (TABS.get(tab.id) || {}).task || null, at: Date.now() });
  } catch { /* ignore malformed urls */ }
}
function otherTabs(me, limit = 10) {
  return [...TABS.entries()].filter(([id]) => id !== me).sort((a, b) => b[1].at - a[1].at).slice(0, limit)
    .map(([, t]) => ({ origin: t.origin, title: t.title }));
}

async function api(path, init = {}) {
  const { token, backend_url } = await settings();
  const headers = { ...(init.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(`${backendOrigin(backend_url)}${path}`, { ...init, headers });
}

async function postJSON(path, body) {
  const r = await api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// ---------------------------------------------------------------- watched sites
async function register(origin) {
  const id = scriptId(origin);
  const existing = await chrome.scripting.getRegisteredContentScripts({ ids: [id] });
  if (!existing.length) {
    await chrome.scripting.registerContentScripts([{ id, matches: [patternFor(origin)], js: SCRIPTS, runAt: "document_idle", allFrames: false, persistAcrossSessions: true }]);
  }
}

async function registerAll() {
  const existing = await chrome.scripting.getRegisteredContentScripts({ ids: [ALL_ID] });
  if (!existing.length) {
    await chrome.scripting.registerContentScripts([{ id: ALL_ID, matches: ALL_MATCHES, js: SCRIPTS, runAt: "document_idle", allFrames: false, persistAcrossSessions: true }]);
  }
}

async function syncRegistrations() {
  const { watched, watch_all } = await settings();
  const granted = [];
  for (const origin of watched) {
    if (await chrome.permissions.contains({ origins: [patternFor(origin)] })) { await register(origin); granted.push(origin); }
  }
  const keep = new Set(granted.map(scriptId));
  let allOn = !!watch_all;
  if (allOn && (await chrome.permissions.contains({ origins: ALL_MATCHES }))) { await registerAll(); keep.add(ALL_ID); }
  else allOn = false;
  const all = await chrome.scripting.getRegisteredContentScripts();
  const stale = all.filter((s) => s.id.startsWith("pl-") && !keep.has(s.id)).map((s) => s.id);
  if (stale.length) await chrome.scripting.unregisterContentScripts({ ids: stale });
  const patch = {};
  if (granted.length !== watched.length) patch.watched = granted;
  if (allOn !== !!watch_all) patch.watch_all = allOn;
  if (Object.keys(patch).length) await chrome.storage.local.set(patch);
}

async function watch(origin, tabId) {
  if (!(await chrome.permissions.contains({ origins: [patternFor(origin)] }))) return { ok: false, error: "permission not granted" };
  const { watched } = await settings();
  if (!watched.includes(origin)) await chrome.storage.local.set({ watched: [...watched, origin] });
  await register(origin);
  if (tabId != null) await chrome.scripting.executeScript({ target: { tabId }, files: SCRIPTS }).catch(() => {});
  return { ok: true };
}

async function unwatch(origin) {
  const { watched } = await settings();
  await chrome.storage.local.set({ watched: watched.filter((o) => o !== origin) });
  await chrome.scripting.unregisterContentScripts({ ids: [scriptId(origin)] }).catch(() => {});
  await chrome.permissions.remove({ origins: [patternFor(origin)] }).catch(() => {});
  return { ok: true };
}

async function watchAll() {
  if (!(await chrome.permissions.contains({ origins: ALL_MATCHES }))) return { ok: false, error: "permission not granted" };
  await chrome.storage.local.set({ watch_all: true, cross_tab: true });
  await registerAll();
  // Inject into every open tab now (ids need no "tabs" permission); pages that reject injection pick it up on reload.
  const tabs = await chrome.tabs.query({}).catch(() => []);
  for (const t of tabs) {
    if (t && t.id != null) await chrome.scripting.executeScript({ target: { tabId: t.id }, files: SCRIPTS }).catch(() => {});
  }
  return { ok: true };
}

async function unwatchAll() {
  await chrome.storage.local.set({ watch_all: false });
  await chrome.scripting.unregisterContentScripts({ ids: [ALL_ID] }).catch(() => {});
  await chrome.permissions.remove({ origins: ALL_MATCHES }).catch(() => {});
  return { ok: true };
}

// ---------------------------------------------------------------- page data
let tasksCache = null;
async function tasks() {
  if (tasksCache) return tasksCache;
  const r = await api("/tasks");
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  tasksCache = await r.json();
  return tasksCache;
}

const CACHE_KEY = "assist_cache";
async function assist(sender, task) {
  const origin = new URL(sender.tab.url).origin;
  const { cloud_recall, paused } = await settings();
  if (paused) return { ok: true, paused: true, data: { page_rules: [], context: [], tab_matches: [] } };
  snapTab(sender.tab);
  const key = `${origin}|${task}`;
  try {
    const data = await postJSON("/assist", { origin, task, recall: !!cloud_recall, open_tabs: otherTabs(sender.tab.id) });
    const cache = (await chrome.storage.local.get(CACHE_KEY))[CACHE_KEY] || {};
    cache[key] = { at: Date.now(), data };
    await chrome.storage.local.set({ [CACHE_KEY]: cache });
    return { ok: true, live: true, data };
  } catch (e) {
    const cache = (await chrome.storage.local.get(CACHE_KEY))[CACHE_KEY] || {};
    if (cache[key]) return { ok: true, live: false, data: cache[key].data, error: String(e) };
    return { ok: false, error: String(e) };
  }
}

// Cross-tab facts: { [tabId]: { origin, title, task, fields: { semantic: { hash, tail } } } }
const FACTS = "tab_facts";
async function observe(sender, msg) {
  const { cross_tab, paused } = await settings();
  snapTab(sender.tab);
  const snap = TABS.get(sender.tab.id);
  if (snap) snap.task = msg.task;
  if (paused || !cross_tab) return { ok: true, conflicts: [] };
  const all = (await chrome.storage.session.get(FACTS))[FACTS] || {};
  const me = String(sender.tab.id);
  const mine = all[me] || { fields: {} };
  mine.origin = new URL(sender.tab.url).origin;
  mine.title = (sender.tab.title || "").slice(0, 80);
  mine.task = msg.task;
  for (const f of msg.fields || []) {
    if (!/^(phone|email|city)$/.test(f.semantic) || typeof f.hash !== "string") continue;
    if (f.hash) mine.fields[f.semantic] = { hash: f.hash, tail: String(f.tail || "").slice(-4) };
    else delete mine.fields[f.semantic];
  }
  all[me] = mine;
  await chrome.storage.session.set({ [FACTS]: all });
  const conflicts = [];
  for (const [tid, other] of Object.entries(all)) {
    if (tid === me || !(other.task === "profile_edit" || other.task === mine.task)) continue;
    for (const [sem, v] of Object.entries(mine.fields)) {
      const o = other.fields[sem];
      if (o && o.hash !== v.hash) conflicts.push({ semantic: sem, other_title: other.title, other_origin: other.origin, other_tail: o.tail });
    }
  }
  return { ok: true, conflicts };
}

chrome.tabs.onRemoved.addListener(async (tabId) => {
  TABS.delete(tabId);
  const all = (await chrome.storage.session.get(FACTS))[FACTS] || {};
  if (all[String(tabId)]) { delete all[String(tabId)]; await chrome.storage.session.set({ [FACTS]: all }); }
});
if (chrome.tabs.onActivated) chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  try { snapTab(await chrome.tabs.get(tabId)); } catch { /* tab gone */ }
});
if (chrome.tabs.onUpdated) chrome.tabs.onUpdated.addListener((tabId, info, tab) => { if (info.status === "complete" || info.url || info.title) snapTab(tab); });

chrome.runtime.onInstalled.addListener(() => { syncRegistrations(); });
chrome.runtime.onStartup.addListener(() => { syncRegistrations(); });
chrome.permissions.onRemoved.addListener(() => { syncRegistrations(); });

const fromPage = (sender) => sender.tab && /^https?:/.test(sender.tab.url || "");
chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  const run = (p) => { p.then(reply, (e) => reply({ ok: false, error: String(e) })); return true; };
  switch (msg && msg.type) {
    case "tasks": return fromPage(sender) ? run(tasks().then((data) => ({ ok: true, data }))) : false;
    case "assist": return fromPage(sender) ? run(assist(sender, String(msg.task || "other"))) : false;
    case "feedback": return fromPage(sender) ? run(postJSON("/feedback", { rule_id: String(msg.rule_id || ""), action: String(msg.action || "") }).then(() => ({ ok: true }))) : false;
    case "observe": return fromPage(sender) ? run(observe(sender, msg)) : false;
    case "settings": return fromPage(sender) ? run(settings().then(({ hold_submit, cross_tab, paused }) => ({ ok: true, hold_submit, cross_tab, paused }))) : false;
    // Popup-only messages (no sender.tab).
    case "watch": return !sender.tab ? run(watch(String(msg.origin), msg.tabId)) : false;
    case "unwatch": return !sender.tab ? run(unwatch(String(msg.origin))) : false;
    case "watchAll": return !sender.tab ? run(watchAll()) : false;
    case "unwatchAll": return !sender.tab ? run(unwatchAll()) : false;
    case "pause": return !sender.tab ? run(chrome.storage.local.set({ paused: true }).then(() => ({ ok: true }))) : false;
    case "unpause": return !sender.tab ? run(chrome.storage.local.set({ paused: false }).then(() => ({ ok: true }))) : false;
    default: return false;
  }
});
