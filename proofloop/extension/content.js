// ProofLoop content script: one quiet, dismissible chip. No chat box.
(async () => {
  if (window.top !== window || document.getElementById("proofloop-chip-host")) return;

  console.info("[ProofLoop] content script running; chip is bottom-right");
  // Never fail silently: if the background worker is missing or the extension was reloaded without
  // reloading this page, still show a chip that says so.
  let res;
  try {
    res = await chrome.runtime.sendMessage({ type: "augment" });
  } catch (e) {
    res = { ok: false, related: [], error: `extension background not responding: ${e && e.message ? e.message : e}. Reload the extension, then reload this page` };
  }
  if (!res) res = { ok: false, related: [], error: "no response from extension background. Reload the extension, then reload this page" };

  const host = document.createElement("div");
  host.id = "proofloop-chip-host";
  host.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;";
  const root = host.attachShadow({ mode: "open" });
  const el = (tag, props = {}, ...kids) => {
    const n = Object.assign(document.createElement(tag), props);
    kids.forEach((k) => n.append(k));
    return n;
  };

  const css = `
    .chip{font:13px system-ui,sans-serif;background:#0b3d2e;color:#fff;border-radius:18px;padding:8px 14px;
      box-shadow:0 2px 10px rgba(0,0,0,.3);cursor:pointer;max-width:420px}
    .x{margin-left:10px;opacity:.7;cursor:pointer}
    .panel{font:12px system-ui,sans-serif;background:#fff;color:#1b1f24;border:1px solid #d0d7de;border-radius:8px;
      padding:10px;margin-bottom:8px;max-width:520px;box-shadow:0 2px 10px rgba(0,0,0,.2)}
    table{border-collapse:collapse;width:100%}td,th{border:1px solid #d0d7de;padding:3px 6px;text-align:left}
    .promoted{color:#1a7f37}.rolled_back{color:#cf222e}.small{opacity:.7;margin-top:6px}
    button{margin-top:6px;cursor:pointer}`;
  // Constructed stylesheets are not blocked by a page's style-src CSP; fall back to a <style> element.
  const style = el("style", { textContent: css });
  try {
    const sheet = new CSSStyleSheet();
    sheet.replaceSync(css);
    root.adoptedStyleSheets = [sheet];
    style.textContent = "";
  } catch { /* keep the <style> fallback */ }

  const d = res.ok ? res.data : null;
  const relCount = res.related.length;
  let label;
  if (!d) label = `ProofLoop: no data (${res.error}). Is the backend running with PROOFLOOP_EXTENSION_ID set? - ${relCount} local tabs shown`;
  else if (!d.active_version) label = `ProofLoop: no current replay record - ${relCount} local tabs shown`;
  else label = `ProofLoop ${d.active_version}: deterministic replay (${d.pass}/${d.total} replay pass) - ${relCount} local tab${relCount === 1 ? "" : "s"} shown`;

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
      t.append(el("tr", {}, ...["Version", "Pass", "Delta", "Replay gate", "Senso node", "Status"].map((h) => el("th", { textContent: h }))));
      for (const e of d.history) {
        t.append(el("tr", {},
          el("td", { textContent: e.version }),
          el("td", { textContent: `${e.tasks_passed_before}/${e.total_tasks} -> ${e.tasks_passed_after}/${e.total_tasks}` }),
          el("td", { textContent: (e.delta >= 0 ? "+" : "") + e.delta.toFixed(2) }),
          el("td", { textContent: e.replay_gate.choice }),
          el("td", { textContent: e.senso_kb_node_id || "-" }),
          el("td", { className: e.status, textContent: e.status })));
      }
      panel.append(t);
    } else {
      panel.append(el("div", { textContent: "No ledger entries. Run harness/replay_loop.py --reset." }));
    }
    panel.append(el("div", { className: "small", textContent: "Other tabs (local opt-in): " + (res.related.map((r) => r.title || r.url).join(" | ") || "none") }));
    if (d) panel.append(el("div", { className: "small", textContent: Object.values(d.services).map((s) => s.label).join(" / ") }));
    panel.append(el("div", { className: "small", textContent: "Measured deterministic replay only. No page data sent to backend or sponsors." }));
    if (d?.retrieval) panel.append(el("div", { className: "small", textContent: "Retrieval readback: " + (d.retrieval.verified ? d.retrieval.mode : "not confirmed") }));
    root.insertBefore(panel, chip);
  };

  root.append(style, chip);
  document.documentElement.append(host);
})();
