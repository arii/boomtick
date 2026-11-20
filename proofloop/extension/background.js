// Fixed loopback backend. /augment and /prompt are GETs with no page data. /assist receives only the
// page origin and path (no query string, no title, no body); /feedback receives a card id and an action.
const BACKEND = "http://127.0.0.1:8787";

async function api(path, init = {}) {
  const { token = "" } = await chrome.storage.local.get("token");
  const headers = { ...(init.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(`${BACKEND}${path}`, { ...init, headers });
}

const CARD_KEY = "cards_cache";

async function assist(sender) {
  let u;
  try { u = new URL(sender.tab && sender.tab.url); } catch { return { ok: false, error: "no tab url" }; }
  if (u.protocol !== "https:" && u.protocol !== "http:") return { ok: false, error: "unsupported scheme" };
  const key = u.origin + u.pathname;
  try {
    const r = await api("/assist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ origin: u.origin, path: u.pathname }) });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    const cache = (await chrome.storage.local.get(CARD_KEY))[CARD_KEY] || {};
    cache[key] = { at: Date.now(), data };
    await chrome.storage.local.set({ [CARD_KEY]: cache });
    return { ok: true, live: true, data };
  } catch (e) {
    // Offline: reuse the last cards fetched for this page so the local matcher keeps working.
    const cache = (await chrome.storage.local.get(CARD_KEY))[CARD_KEY] || {};
    if (cache[key]) return { ok: true, live: false, data: cache[key].data, error: String(e) };
    return { ok: false, error: String(e) };
  }
}

async function feedback(msg) {
  try {
    const r = await api("/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ card_id: String(msg.card_id || ""), action: String(msg.action || "") }) });
    return { ok: r.ok };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

async function augment(senderTab) {
  const { local_related_tabs = false } = await chrome.storage.local.get("local_related_tabs");
  let related = [];
  if (local_related_tabs) {
    const tabs = await chrome.tabs.query({ windowId: senderTab.windowId });
    related = tabs.filter(t => t.id !== senderTab.id && /^https?:/.test(t.url || ""))
      .slice(0, 5).map(t => ({ title: t.title || "", url: t.url }));
  }
  try {
    const r = await api("/augment");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return { ok: true, related, data: await r.json() };
  } catch (e) {
    return { ok: false, related, error: String(e) };
  }
}

async function fetchPrompt() {
  try {
    const r = await api("/prompt");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return { ok: true, data: await r.json() };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg?.type === "prompt" && sender.tab) {
    fetchPrompt().then(sendResponse);
    return true;
  }
  if (msg?.type === "assist" && sender.tab) {
    assist(sender).then(sendResponse);
    return true;
  }
  if (msg?.type === "feedback" && sender.tab) {
    feedback(msg).then(sendResponse);
    return true;
  }
  if (msg?.type === "augment" && sender.tab) {
    augment(sender.tab).then(sendResponse);
    return true;
  }
});
