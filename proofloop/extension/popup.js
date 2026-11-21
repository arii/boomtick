const $ = (id) => document.getElementById(id);
(async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  let origin = null;
  try { const u = new URL(tab.url); if (/^https?:$/.test(u.protocol)) origin = u.origin; } catch { /* not a web page */ }
  if (!origin) { $("site").textContent = "Not a web page."; return; }
  $("site").textContent = origin;
  const { watched = [] } = await chrome.storage.local.get("watched");
  const pattern = `${new URL(origin).protocol}//${new URL(origin).hostname}/*`;
  const on = watched.includes(origin) && (await chrome.permissions.contains({ origins: [pattern] }));
  const t = $("toggle");
  t.hidden = false;
  t.textContent = on ? "Stop watching this site" : "Watch this site";
  if (on) {
    try {
      const s = await chrome.tabs.sendMessage(tab.id, { type: "state" });
      $("state").textContent = s ? `Task: ${s.task.replaceAll("_", " ")} · ${s.rules} rule${s.rules === 1 ? "" : "s"} · ${s.conflicts} open conflict${s.conflicts === 1 ? "" : "s"}` : "";
    } catch { $("state").textContent = "Reload the page to start watching it."; }
  }
  t.onclick = async () => {
    if (on) {
      await chrome.runtime.sendMessage({ type: "unwatch", origin });
      $("state").textContent = "Stopped. Reload the page to remove ProofLoop from it.";
    } else {
      // The permission prompt must come from this click.
      const ok = await chrome.permissions.request({ origins: [pattern] });
      if (!ok) { $("state").textContent = "Permission not granted."; return; }
      const r = await chrome.runtime.sendMessage({ type: "watch", origin, tabId: tab.id });
      $("state").textContent = r && r.ok ? "Watching. Warnings appear on this page when something conflicts with your rules." : `Could not watch: ${r && r.error}`;
    }
    t.hidden = true;
  };
})();
