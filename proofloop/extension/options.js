const $ = (id) => document.getElementById(id);
const DEFAULT_BACKEND = "http://127.0.0.1:8787";
// Normalized http(s) origin of the typed URL, or null when it is not a usable backend URL.
function backendOrigin(value) {
  try {
    const u = new URL(String(value || "").trim() || DEFAULT_BACKEND);
    return /^https?:$/.test(u.protocol) ? u.origin : null;
  } catch { return null; }
}
const DEFAULTS = { token: "", backend_url: DEFAULT_BACKEND, hold_submit: true, cross_tab: false, cloud_recall: false, watched: [] };
(async () => {
  const s = await chrome.storage.local.get(DEFAULTS);
  $("token").value = s.token;
  $("backend_url").value = backendOrigin(s.backend_url) || DEFAULT_BACKEND;
  for (const k of ["hold_submit", "cross_tab", "cloud_recall"]) $(k).checked = !!s[k];
  for (const o of s.watched) $("watched").append(Object.assign(document.createElement("li"), { textContent: o }));
  if (!s.watched.length) $("watched").append(Object.assign(document.createElement("li"), { textContent: "None yet. Use the toolbar button on a site." }));
  try {
    const r = await fetch(`${backendOrigin(s.backend_url) || DEFAULT_BACKEND}/status`, { headers: s.token ? { Authorization: `Bearer ${s.token}` } : {} });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const status = await r.json();
    $("status").textContent = "";
    for (const v of Object.values(status)) $("status").append(Object.assign(document.createElement("div"), { textContent: `${v.label} (${v.mode})` }));
  } catch (e) {
    $("status").textContent = `Backend unavailable (${e.message}). Start harness/server.py (or fix the backend URL below) with PROOFLOOP_EXTENSION_ID=${chrome.runtime.id} and paste the token below.`;
  }
})();
$("save").onclick = async () => {
  const backend = backendOrigin($("backend_url").value);
  if (!backend) { $("msg").textContent = "Backend URL must start with http:// or https://."; return; }
  // Requested first so it runs inside the click's user gesture. The default loopback backend is already in host_permissions.
  if (backend !== DEFAULT_BACKEND) {
    const u = new URL(backend);
    const granted = await chrome.permissions.request({ origins: [`${u.protocol}//${u.hostname}/*`] });
    if (!granted) { $("msg").textContent = `Not saved: permission to reach ${u.hostname} was not granted.`; return; }
  }
  await chrome.storage.local.set({ backend_url: backend, token: $("token").value.trim(), hold_submit: $("hold_submit").checked, cross_tab: $("cross_tab").checked, cloud_recall: $("cloud_recall").checked });
  $("msg").textContent = "Saved. Reload watched pages to apply.";
};
