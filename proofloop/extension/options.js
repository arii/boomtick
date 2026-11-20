const FIELDS = ["backend_url", "SENSO_API_KEY", "TYPESAFE_API_KEY", "COGNEE_API_URL", "OPENROUTER_API_KEY"];
const $ = (id) => document.getElementById(id);

async function backend() {
  return ($("backend_url").value || "http://127.0.0.1:8787").replace(/\/$/, "");
}

async function refreshStatus() {
  const box = $("status");
  box.textContent = "";
  try {
    const s = await (await fetch(`${await backend()}/status`)).json();
    for (const v of Object.values(s)) {
      const b = document.createElement("span");
      b.className = "badge" + (v.mode === "live" ? " live" : "");
      b.textContent = v.label;
      box.append(b);
    }
  } catch (e) {
    box.textContent = "Backend unreachable: start `python3 harness/server.py`";
  }
}

(async () => {
  const saved = await chrome.storage.local.get(FIELDS);
  FIELDS.forEach((f) => { if (saved[f]) $(f).value = saved[f]; });
  refreshStatus();
})();

$("save").onclick = async () => {
  const vals = Object.fromEntries(FIELDS.map((f) => [f, $(f).value.trim()]));
  await chrome.storage.local.set(vals);
  const { backend_url, ...keys } = vals;
  try {
    const r = await fetch(`${await backend()}/config`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(keys),
    });
    $("msg").textContent = r.ok ? "Saved and synced to backend." : `Saved locally; backend returned ${r.status}.`;
  } catch {
    $("msg").textContent = "Saved locally; backend unreachable.";
  }
  refreshStatus();
};
