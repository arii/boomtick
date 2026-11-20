// Page assistant. On a form field the user edits, checks the value against the rule cards the backend
// returned for this page and, if it breaks one, shows a small chip next to the field with a fix and a
// citation. It never edits a field unless the user clicks the fix. Page text is only ever inserted with
// textContent; the chip lives in a closed shadow root so page scripts cannot read or restyle it.
(async () => {
  if (window.top !== window || window.__proofloopAssist) return;
  window.__proofloopAssist = true;
  const { classify } = globalThis.ProofLoopDetect;
  const { evaluate } = globalThis.ProofLoopMatch;

  let res;
  try { res = await chrome.runtime.sendMessage({ type: "assist" }); } catch (e) { res = { ok: false, error: String(e && e.message || e) }; }
  const set = res && res.ok ? res.data : null;
  const cards = set ? set.cards : [];

  const dismissed = new WeakMap(); // field -> Set of "cardId|value" the user chose to keep
  const reported = new Set();
  let current = null; // { field, hit, card }
  let host = null, root = null, panel = null, raf = 0;

  const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); kids.forEach((k) => n.append(k)); return n; };

  const CSS = `
    .chip{all:initial;display:block;box-sizing:border-box;width:320px;font:13px/1.4 system-ui,sans-serif;background:#fff;color:#1b1f24;
      border:1px solid #bf8700;border-left:4px solid #bf8700;border-radius:8px;padding:10px 12px;box-shadow:0 4px 14px rgba(0,0,0,.25)}
    .msg{font-weight:600;margin-bottom:4px}
    .src{font-size:11px;color:#57606a;margin-bottom:8px}
    .row{display:flex;gap:8px}
    button{font:inherit;font-size:12px;padding:4px 10px;border-radius:6px;border:1px solid #d0d7de;background:#f6f8fa;color:#1b1f24;cursor:pointer}
    button.use{background:#0b3d2e;color:#fff;border-color:#0b3d2e}`;

  function ensureHost() {
    if (host) return;
    host = el("div", { id: "proofloop-assist-host" });
    host.style.cssText = "position:fixed;left:0;top:0;z-index:2147483647;display:none;";
    root = host.attachShadow({ mode: "closed" });
    root.append(el("style", { textContent: CSS }));
    document.documentElement.append(host);
  }

  function provenance(card) {
    const ids = card.provenance.map((id) => { const m = /^sess_(\d{4})_(\d{2})_(\d{2})_(.+)$/.exec(id); return m ? `${m[4]} ${m[2]}/${m[3]}` : id; });
    return ids.join(", ");
  }

  function position() {
    raf = 0;
    if (!current || !host) return;
    if (!current.field.isConnected) return hide();
    const r = current.field.getBoundingClientRect();
    const h = panel ? panel.offsetHeight : 90;
    const below = r.bottom + 6 + h < window.innerHeight;
    host.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - 336))}px`;
    host.style.top = `${below ? r.bottom + 6 : Math.max(8, r.top - h - 6)}px`;
  }
  const schedule = () => { if (!raf) raf = requestAnimationFrame(position); };

  function hide() {
    current = null;
    if (host) host.style.display = "none";
    if (panel) { panel.remove(); panel = null; }
  }

  function fill(field, value) {
    const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(field), "value").set;
    setter.call(field, value);
    field.dispatchEvent(new Event("input", { bubbles: true }));
    field.dispatchEvent(new Event("change", { bubbles: true }));
  }

  const notify = (card, action) => { try { chrome.runtime.sendMessage({ type: "feedback", card_id: card.id, action }); } catch { /* backend optional */ } };

  function show(field, hit, card) {
    ensureHost();
    if (current && current.field === field && current.hit.card_id === hit.card_id && current.hit.replacement === hit.replacement) return schedule();
    hide();
    current = { field, hit, card };
    const use = el("button", { className: "use", textContent: `Use ${hit.expect}`, title: hit.replacement });
    const keep = el("button", { textContent: "Keep" });
    use.onclick = () => { fill(field, hit.replacement); notify(card, "used_suggestion"); hide(); field.focus(); };
    keep.onclick = () => {
      const s = dismissed.get(field) || new Set(); s.add(`${card.id}|${field.value}`); dismissed.set(field, s);
      notify(card, "kept_value"); hide();
    };
    const live = res.live === false ? " (cached)" : "";
    panel = el("div", { className: "chip", role: "status" },
      el("div", { className: "msg", textContent: hit.message }),
      el("div", { className: "src", textContent: `Rule ${card.id} · set v${set.version}${live} · local rule file · from your ${provenance(card)} sessions` }),
      el("div", { className: "row" }, use, keep));
    root.append(panel);
    host.style.display = "block";
    schedule();
    const key = `${card.id}|${field.value}`;
    if (!reported.has(key)) { reported.add(key); notify(card, "shown"); }
  }

  function check(field) {
    if (!cards.length || !field || field.tagName !== "INPUT") return;
    const c = classify(field);
    if (!c) { if (current && current.field === field) hide(); return; }
    for (const card of cards) {
      const hit = evaluate(card, c.semantic, field.value);
      if (!hit) continue;
      const kept = dismissed.get(field);
      if (kept && kept.has(`${card.id}|${field.value}`)) continue;
      return show(field, hit, card);
    }
    if (current && current.field === field) hide();
  }

  let timer = 0;
  document.addEventListener("input", (e) => { clearTimeout(timer); const f = e.target; timer = setTimeout(() => check(f), 250); }, true);
  document.addEventListener("change", (e) => check(e.target), true);
  document.addEventListener("focusout", (e) => check(e.target), true);
  document.addEventListener("scroll", schedule, true);
  window.addEventListener("resize", schedule);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && current) hide(); }, true);

  if (!set) console.info("[ProofLoop] assistant has no rules for this page:", res && res.error);
})();
