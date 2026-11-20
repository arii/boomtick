// ProofLoop background service worker: related-tab correlation + backend /augment.
const DEFAULT_BACKEND = "http://127.0.0.1:8787";
const STOP = new Set(["the", "a", "an", "of", "and", "to", "for", "in", "on", "is", "-", "|"]);

const tokens = (s) =>
  new Set((s || "").toLowerCase().match(/[a-z0-9]+/g)?.filter((w) => !STOP.has(w) && w.length > 2) || []);

async function backendUrl() {
  const { backend_url } = await chrome.storage.local.get("backend_url");
  return (backend_url || DEFAULT_BACKEND).replace(/\/$/, "");
}

// Other http(s) tabs in the same window, ranked by title overlap with the active page.
async function relatedTabs(senderTab, snippet) {
  const tabs = await chrome.tabs.query({ windowId: senderTab.windowId });
  const mine = tokens(`${senderTab.title} ${snippet}`);
  return tabs
    .filter((t) => t.id !== senderTab.id && /^https?:/.test(t.url || ""))
    .map((t) => ({ title: t.title || "", url: t.url, overlap: [...tokens(t.title)].filter((w) => mine.has(w)).length }))
    .sort((a, b) => b.overlap - a.overlap)
    .slice(0, 5);
}

async function augment(msg, senderTab) {
  const related = await relatedTabs(senderTab, msg.snippet);
  const base = await backendUrl();
  const qs = new URLSearchParams({ title: msg.title, url: msg.url });
  try {
    const r = await fetch(`${base}/augment?${qs}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return { ok: true, related, data: await r.json() };
  } catch (e) {
    return { ok: false, related, error: String(e) };
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg?.type === "augment" && sender.tab) {
    augment(msg, sender.tab).then(sendResponse);
    return true; // async response
  }
});
