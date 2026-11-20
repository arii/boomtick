const $ = id => document.getElementById(id);
(async () => {
  const { local_related_tabs = false } = await chrome.storage.local.get("local_related_tabs");
  $("local_related_tabs").checked = local_related_tabs;
  try {
    const r = await fetch("http://127.0.0.1:8787/status");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const status = await r.json();
    $("status").textContent = "";
    for (const service of Object.values(status)) {
      const row = document.createElement("div");
      row.textContent = service.label;
      $("status").append(row);
    }
  } catch {
    $("status").textContent = "Backend unavailable or extension origin not enabled. Start the read-only backend with this extension's exact ID.";
  }
})();
$("save").onclick = async () => {
  await chrome.storage.local.set({ local_related_tabs: $("local_related_tabs").checked });
  $("msg").textContent = "Local setting saved. No credentials collected.";
};
