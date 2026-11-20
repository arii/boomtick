// Fixed loopback status endpoint. Never send page titles, URLs or snippets.
const BACKEND = "http://127.0.0.1:8787";

async function augment(senderTab) {
  const { local_related_tabs = false } = await chrome.storage.local.get("local_related_tabs");
  let related = [];
  if (local_related_tabs) {
    const tabs = await chrome.tabs.query({ windowId: senderTab.windowId });
    related = tabs.filter(t => t.id !== senderTab.id && /^https?:/.test(t.url || ""))
      .slice(0, 5).map(t => ({ title: t.title || "", url: t.url }));
  }
  try {
    const r = await fetch(`${BACKEND}/augment`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return { ok: true, related, data: await r.json() };
  } catch (e) {
    return { ok: false, related, error: String(e) };
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg?.type === "augment" && sender.tab) {
    augment(sender.tab).then(sendResponse);
    return true;
  }
});
