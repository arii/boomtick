// ProofLoop content script: one quiet, dismissible chip. No chat box.
(async () => {
  if (window.top !== window || document.getElementById("proofloop-chip-host")) return;

  // Optional Chrome built-in AI: pre-filter snippet locally; backend path otherwise.
  async function localAssist(text) {
    try {
      if (typeof LanguageModel === "undefined") return { used: false, text };
      const avail = await LanguageModel.availability();
      if (avail !== "available") return { used: false, text };
      const s = await LanguageModel.create();
      const out = await s.prompt("Return the 300 most relevant characters of this text, verbatim:\n" + text.slice(0, 2000));
      return { used: true, text: String(out).slice(0, 400) };
    } catch {
      return { used: false, text };
    }
  }

  const raw = (document.body?.innerText || "").replace(/\s+/g, " ").slice(0, 600);
  const assist = await localAssist(raw);
  const res = await chrome.runtime.sendMessage({
    type: "augment", title: document.title, url: location.href, snippet: assist.text,
  });
  if (!res) return;

  const host = document.createElement("div");
  host.id = "proofloop-chip-host";
  host.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;";
  const root = host.attachShadow({ mode: "open" });
  const el = (tag, props = {}, ...kids) => {
    const n = Object.assign(document.createElement(tag), props);
    kids.forEach((k) => n.append(k));
    return n;
  };

  const style = el("style", {
    textContent: `
    .chip{font:13px system-ui,sans-serif;background:#0b3d2e;color:#fff;border-radius:18px;padding:8px 14px;
      box-shadow:0 2px 10px rgba(0,0,0,.3);cursor:pointer;max-width:420px}
    .x{margin-left:10px;opacity:.7;cursor:pointer}
    .panel{font:12px system-ui,sans-serif;background:#fff;color:#1b1f24;border:1px solid #d0d7de;border-radius:8px;
      padding:10px;margin-bottom:8px;max-width:520px;box-shadow:0 2px 10px rgba(0,0,0,.2)}
    table{border-collapse:collapse;width:100%}td,th{border:1px solid #d0d7de;padding:3px 6px;text-align:left}
    .promoted{color:#1a7f37}.rolled_back{color:#cf222e}.small{opacity:.7;margin-top:6px}
    button{margin-top:6px;cursor:pointer}`,
  });

  const d = res.ok ? res.data : null;
  const relCount = res.related.length;
  let label;
  if (!d) label = `ProofLoop backend unreachable (${res.error}) - cross-tab: ${relCount} related tabs`;
  else if (!d.active_version) label = `ProofLoop: no verified skill yet - cross-tab: ${relCount} related tabs`;
  else label = `ProofLoop ${d.active_version} verified (${d.pass}/${d.total} replay pass) - cross-tab: ${relCount} related tab${relCount === 1 ? "" : "s"} detected`;

  const chip = el("div", { className: "chip" }, el("span", { textContent: label }));
  const close = el("span", { className: "x", textContent: "x", title: "Dismiss" });
  close.onclick = (e) => { e.stopPropagation(); host.remove(); };
  chip.append(close);

  let panel = null;
  chip.onclick = () => {
    if (panel) { panel.remove(); panel = null; return; }
    panel = el("div", { className: "panel" });
    if (d && d.history.length) {
      const t = el("table");
      t.append(el("tr", {}, ...["Version", "Pass", "Delta", "Gate", "Senso node", "Status"].map((h) => el("th", { textContent: h }))));
      for (const e of d.history) {
        t.append(el("tr", {},
          el("td", { textContent: e.version }),
          el("td", { textContent: `${e.tasks_passed_before}/${e.total_tasks} -> ${e.tasks_passed_after}/${e.total_tasks}` }),
          el("td", { textContent: (e.delta >= 0 ? "+" : "") + e.delta.toFixed(2) }),
          el("td", { textContent: `${e.jev_gate.choice} ${e.jev_gate.confidence}` }),
          el("td", { textContent: e.senso_kb_node_id || "-" }),
          el("td", { className: e.status, textContent: e.status })));
      }
      panel.append(t);
    } else {
      panel.append(el("div", { textContent: "No ledger entries. Run harness/replay_loop.py --reset." }));
    }
    panel.append(el("div", { className: "small", textContent: "Related tabs: " + (res.related.map((r) => r.title || r.url).join(" | ") || "none") }));
    if (d) panel.append(el("div", { className: "small", textContent: Object.values(d.services).map((s) => s.label).join(" / ") }));
    panel.append(el("div", { className: "small", textContent: "Local assist (Gemini Nano): " + (assist.used ? "used" : "unavailable, backend path") }));
    root.insertBefore(panel, chip);
  };

  root.append(style, chip);
  document.documentElement.append(host);
})();
