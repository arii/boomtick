const $ = (id) => document.getElementById(id);
const DEFAULTS = { token: "", hold_submit: true, cross_tab: false, cloud_recall: false, watched: [] };
(async () => {
  const s = await chrome.storage.local.get(DEFAULTS);
  $("token").value = s.token;
  for (const k of ["hold_submit", "cross_tab", "cloud_recall"]) $(k).checked = !!s[k];
  for (const o of s.watched) $("watched").append(Object.assign(document.createElement("li"), { textContent: o }));
  if (!s.watched.length) $("watched").append(Object.assign(document.createElement("li"), { textContent: "None yet. Use the toolbar button on a site." }));
  try {
    const r = await fetch("http://127.0.0.1:8787/status", { headers: s.token ? { Authorization: `Bearer ${s.token}` } : {} });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const status = await r.json();
    $("status").textContent = "";
    for (const v of Object.values(status)) $("status").append(Object.assign(document.createElement("div"), { textContent: `${v.label} (${v.mode})` }));
  } catch (e) {
    $("status").textContent = `Backend unavailable (${e.message}). Start harness/server.py with PROOFLOOP_EXTENSION_ID=${chrome.runtime.id} and paste the token below.`;
  }
})();
$("save").onclick = async () => {
  await chrome.storage.local.set({ token: $("token").value.trim(), hold_submit: $("hold_submit").checked, cross_tab: $("cross_tab").checked, cloud_recall: $("cloud_recall").checked });
  $("msg").textContent = "Saved. Reload watched pages to apply.";
};
