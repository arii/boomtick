// fallow-ignore-file unused-file
// Reason: content script loaded via chrome.scripting from background.js SCRIPTS, not via import.
// ProofLoop observer. Runs only on sites Ari turned on. It reads form fields (including values set by an agent,
// autofill or a picked suggestion, by polling), works out the page's task, and warns when a field conflicts with a
// promoted rule or with another watched tab. It never types, fills, checks or submits anything. Its only page
// actions: drawing its own UI in a closed shadow root, and (if enabled) holding one submit while a conflict is open.
// Page text is inserted only with textContent.
(async () => {
  if (window.top !== window || window.__proofloopObserver) return;
  window.__proofloopObserver = true;
  const D = globalThis.ProofLoopDetect, M = globalThis.ProofLoopMatch, T = globalThis.ProofLoopTask;
  const send = (m) => chrome.runtime.sendMessage(m).catch((e) => ({ ok: false, error: String(e && e.message || e) }));

  const vocabRes = await send({ type: "tasks" });
  const vocab = vocabRes && vocabRes.ok ? vocabRes.data : { tasks: [] };
  const prefsRes = await send({ type: "settings" });
  const prefs = prefsRes && prefsRes.ok ? prefsRes : { hold_submit: true, cross_tab: false, paused: false };
  // Terminal pages (ttyd/xterm, e.g. 127.0.0.1:8082): pill only, never inline markers over the prompt.
  let terminal = location.port === "8082";
  const sniffTerminal = () => { if (!terminal) terminal = !!document.querySelector(".xterm-screen,.xterm,#terminal"); };

  const S = {
    task: null, res: null, fields: [], conflicts: new Map(), // key -> { el, hit, rule }
    dismissed: new Set(), shown: new Set(), cross: [], panelOpen: false, pending: null, bypass: false, error: vocabRes.ok ? "" : vocabRes.error,
  };
  const rulesNow = () => (S.res && S.res.ok && S.res.data.page_rules) || [];
  const visible = (el) => el.isConnected && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden";
  const fieldState = (f) => ({ semantic: f.semantic, label: f.label, value: f.el.value, checked: !!f.el.checked });
  // Warnings are keyed by the field element itself, not its position: sites insert and remove fields as they
  // re-render, and a position-based key made dismissed warnings come back and "shown" feedback repeat.
  const ids = new WeakMap();
  let nextId = 0;
  const fieldId = (el) => { if (!ids.has(el)) ids.set(el, ++nextId); return ids.get(el); };
  const keyOf = (rid, f) => `${rid}|${fieldId(f.el)}`;
  const dismissKey = (rid, f) => `${rid}|${fieldId(f.el)}|${f.el.type === "checkbox" || f.el.type === "radio" ? f.el.checked : f.el.value}`;

  // ------------------------------------------------------------------ UI scaffolding
  const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); kids.forEach((k) => k != null && n.append(k)); return n; };
  const host = el("div", { id: "proofloop-observer-host" });
  host.style.cssText = "all:initial;position:fixed;left:0;top:0;width:0;height:0;z-index:2147483647;";
  const root = host.attachShadow({ mode: "closed" });
  const CSS = `
    *{box-sizing:border-box}
    .pill{position:fixed;font:12px/1.3 system-ui,sans-serif;background:#1b1f24;color:#fff;border-radius:14px;
      padding:6px 12px;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.3);border:0}
    .pill.warn{background:#9a6700}
    .panel{position:fixed;width:340px;max-height:60vh;overflow:auto;font:12px/1.4 system-ui,sans-serif;background:#fff;color:#1b1f24;
      border:1px solid #d0d7de;border-radius:10px;padding:10px;box-shadow:0 6px 20px rgba(0,0,0,.25)}
    h4{margin:8px 0 4px;font-size:12px}
    .card{border:1px solid #d0d7de;border-radius:8px;padding:8px;margin:6px 0}
    .card.warn{border-left:4px solid #bf8700}
    .msg{font-weight:600}
    .tag{font-size:11px;color:#57606a;margin-top:2px}
    .row{display:flex;gap:6px;margin-top:6px;flex-wrap:wrap}
    button.b{font:inherit;font-size:11px;padding:3px 8px;border-radius:6px;border:1px solid #d0d7de;background:#f6f8fa;color:#1b1f24;cursor:pointer}
    button.primary{background:#1b1f24;color:#fff;border-color:#1b1f24}
    .outline{position:fixed;border:2px solid #bf8700;border-radius:6px;pointer-events:none}
    .chip{position:fixed;margin:0;width:280px;font:12px/1.4 system-ui,sans-serif;background:#fff;color:#1b1f24;border:1px solid #bf8700;border-left:4px solid #bf8700;
      border-radius:8px;padding:8px 10px;box-shadow:0 4px 14px rgba(0,0,0,.25)}
    .foot{font-size:11px;color:#57606a;margin-top:8px}`;
  try { const sheet = new CSSStyleSheet(); sheet.replaceSync(CSS); root.adoptedStyleSheets = [sheet]; } catch { root.append(el("style", { textContent: CSS })); }
  const layer = el("div");
  root.append(layer);
  document.documentElement.append(host);

  // ------------------------------------------------------------------ text helpers
  const sessionDate = (id) => { const m = /^sess_(\d{4})_(\d{2})_(\d{2})_/.exec(id); return m ? `${m[2]}/${m[3]}` : id; };
  const sourceShort = () => {
    const d = S.res && S.res.data;
    if (!d || !d.version) return "no rule set";
    return `${d.version} · ${d.source.kind === "senso" ? "Senso rule" : d.source.kind === "senso-copy" ? "Senso rule (local copy)" : d.source.label}${S.res.live ? "" : " · cached"}`;
  };
  const ruleTag = (rule) => `Rule ${rule.id} · ${sourceShort()} · from sessions ${rule.provenance.map(sessionDate).join(", ")}`;
  const notify = (rule_id, action) => send({ type: "feedback", rule_id, action });

  // ------------------------------------------------------------------ placement: next to the field, covering as few fields as possible
  // Hard obstacles (never covered): fields, buttons, links, and UI already placed. Soft obstacles: label text.
  function obstacles(except, placed) {
    const hard = placed.slice(), soft = [];
    for (const b of document.querySelectorAll("button, [role=button], input[type=submit], input[type=button], a[href], input, select, textarea")) {
      if (b !== except && visible(b)) hard.push(b.getBoundingClientRect());
    }
    for (const f of S.fields) if (f.el.labels) for (const l of f.el.labels) soft.push(l.getBoundingClientRect());
    return { hard, soft };
  }
  const overlap = (a, b) => Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  function place(fieldEl, w, h, placed = []) {
    const r = fieldEl.getBoundingClientRect(), vw = innerWidth, vh = innerHeight, g = 8;
    // Beside the field, then beside the form or dialog that holds it (where centered forms leave free space),
    // each also shifted up so the chip ends level with the field.
    const box = (fieldEl.closest("form, [role=dialog], fieldset") || fieldEl.parentElement || fieldEl).getBoundingClientRect();
    const xs = [r.right + g, r.left - w - g, box.right + g, box.left - w - g];
    const opts = [];
    for (const x of xs) opts.push({ left: x, top: r.top }, { left: x, top: r.bottom - h });
    opts.push({ left: r.left, top: r.bottom + g }, { left: r.left, top: r.top - h - g });
    const { hard, soft } = obstacles(fieldEl, placed);
    hard.push(r);
    let best = null;
    for (const o of opts) {
      const b = { left: o.left, top: o.top, right: o.left + w, bottom: o.top + h };
      if (b.left < 4 || b.top < 4 || b.right > vw - 4 || b.bottom > vh - 4) continue;
      const pad = { left: b.left - 4, top: b.top - 4, right: b.right + 4, bottom: b.bottom + 4 }; // 4px clearance
      if (hard.some((x) => overlap(pad, x) > 0)) continue;
      const cost = soft.reduce((s, x) => s + overlap(b, x), 0);
      if (!best || cost < best.cost) best = { ...o, cost };
    }
    return best; // null: no spot that leaves every control visible
  }

  // ------------------------------------------------------------------ render
  function conflictCard(c, opts = {}) {
    const got = el("button", { className: "b", textContent: "Got it" });
    const wrong = el("button", { className: "b", textContent: "Rule is wrong" });
    got.onclick = () => { S.dismissed.add(c.dismiss); notify(c.rule.id, "dismissed"); refresh(); };
    wrong.onclick = () => { S.dismissed.add(c.dismiss); notify(c.rule.id, "rule_wrong"); refresh(); };
    const detail = c.hit.found ? ` (found: ${c.hit.found}${c.hit.expect ? `; your sessions say ${c.hit.expect}` : ""})` : "";
    return el("div", { className: `card warn${opts.chip ? " chip" : ""}`, role: "status" },
      el("div", { className: "msg", textContent: c.hit.message + detail }),
      el("div", { className: "tag", textContent: ruleTag(c.rule) }),
      el("div", { className: "row" }, got, wrong));
  }

  // A field is drawn around only when it is the topmost thing at its center (not behind a banner or dialog).
  function unobscured(f) {
    const r = f.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) return false;
    const top = document.elementFromPoint(x, y);
    return !!top && (top === f || f.contains(top) || top.contains(f) || (f.labels && [...f.labels].some((l) => l.contains(top))));
  }

  // Pill position: the first spot along the screen edges (bottom-right first, then sliding along the bottom, the
  // right edge, the top and the left) whose box covers no page control. Returns left/top plus which side it hugs.
  function pillCorner(w, h) {
    const m = 16, step = 40;
    const controls = [...document.querySelectorAll("button, [role=button], a[href], input, select, textarea")].filter(visible).map((b) => b.getBoundingClientRect());
    const spots = [];
    for (let x = innerWidth - m - w; x >= m; x -= step) spots.push({ left: x, top: innerHeight - m - h });
    for (let y = innerHeight - m - h; y >= m; y -= step) spots.push({ left: innerWidth - m - w, top: y });
    for (let x = innerWidth - m - w; x >= m; x -= step) spots.push({ left: x, top: m });
    for (let y = innerHeight - m - h; y >= m; y -= step) spots.push({ left: m, top: y });
    const free = spots.find((p) => !controls.some((x) => overlap({ left: p.left - 4, top: p.top - 4, right: p.left + w + 4, bottom: p.top + h + 4 }, x) > 0))
      || spots[0];
    return { left: free.left, top: free.top, rightSide: free.left > innerWidth / 2, bottomSide: free.top > innerHeight / 2,
             box: { left: free.left, top: free.top, right: free.left + w, bottom: free.top + h } };
  }

  const openConflicts = (includeSubmitOnly) => [...S.conflicts.values()].filter((c) => !S.dismissed.has(c.dismiss) && (includeSubmitOnly || !c.hit.atSubmit));

  function render() {
    layer.textContent = "";
    if (prefs.paused) return;
    const live = openConflicts(false);
    const all = openConflicts(true);
    const rules = rulesNow();
    const ctx = (S.res && S.res.ok && S.res.data.context) || [];
    // Inline marker for each conflict shown while editing (submit-time confirmations show only in the panel).
    // Each chip avoids fields, labels, buttons, links, the pill and the chips placed before it.
    const tm = (S.res && S.res.ok && S.res.data.tab_matches) || [];
    const pillLabel = (() => {
      const n = all.length + S.cross.length;
      if (!rules.length && !ctx.length && !tm.length && !n && !S.error) return null;
      if (terminal && !n) return `ProofLoop · ${ctx.length + tm.length} match${ctx.length + tm.length === 1 ? "" : "es"}`;
      return n ? `ProofLoop · ${n} conflict${n === 1 ? "" : "s"}` : S.error && !rules.length ? "ProofLoop · backend unavailable"
        : `ProofLoop · ${rules.length} rule${rules.length === 1 ? "" : "s"}${ctx.length ? ` · ${ctx.length} past` : ""}${tm.length ? ` · ${tm.length} tab${tm.length === 1 ? "" : "s"}` : ""}`;
    })();
    let pill = null, corner = null;
    if (pillLabel) {
      const n = all.length + S.cross.length;
      pill = el("button", { className: `pill${n ? " warn" : ""}`, textContent: pillLabel, title: "Context & Rules" });
      pill.onclick = () => { S.panelOpen = !S.panelOpen; render(); };
      layer.append(pill);
      corner = pillCorner(pill.offsetWidth || 160, pill.offsetHeight || 28);
      pill.style.left = `${corner.left}px`;
      pill.style.top = `${corner.top}px`;
    }
    const placed = corner ? [corner.box] : [];
    if (corner && (S.panelOpen || S.pending)) {
      const px = corner.rightSide ? { left: innerWidth - 380, right: innerWidth } : { left: 0, right: 380 };
      placed.push({ ...px, top: 0, bottom: innerHeight });
    }
    for (const c of (terminal ? [] : live)) {
      if (!visible(c.el) || !unobscured(c.el)) continue;
      const r = c.el.getBoundingClientRect();
      const o = el("div", { className: "outline" });
      Object.assign(o.style, { left: `${r.left - 3}px`, top: `${r.top - 3}px`, width: `${r.width + 6}px`, height: `${r.height + 6}px` });
      const chip = conflictCard(c, { chip: true });
      layer.append(o, chip);
      const h = chip.offsetHeight || 96;
      const p = place(c.el, 280, h, placed);
      if (!p) { chip.remove(); continue; } // the outline stays; the warning is in the pill and panel
      Object.assign(chip.style, { left: `${p.left}px`, top: `${p.top}px` });
      placed.push({ left: p.left, top: p.top, right: p.left + 280, bottom: p.top + h });
    }
    if (!pill) return;
    layer.append(pill); // keep the pill above chips
    if (!S.panelOpen && !S.pending) return;
    const panel = el("div", { className: "panel" });
    const pb = corner.box;
    if (corner.rightSide) panel.style.right = `${Math.max(8, innerWidth - pb.right)}px`; else panel.style.left = `${pb.left}px`;
    if (corner.bottomSide) panel.style.bottom = `${innerHeight - pb.top + 8}px`; else panel.style.top = `${pb.bottom + 8}px`;
    if (S.pending) {
      panel.append(el("h4", { textContent: "Before you submit" }));
      const back = el("button", { className: "b", textContent: "Back to form" });
      const anyway = el("button", { className: "b primary", textContent: "Submit anyway" });
      back.onclick = () => { S.pending = null; S.panelOpen = false; render(); };
      anyway.onclick = () => releaseSubmit();
      panel.append(el("div", { className: "row" }, back, anyway));
    }
    if (all.length) { panel.append(el("h4", { textContent: "Conflicts" })); for (const c of all) panel.append(conflictCard(c)); }
    for (const x of S.cross) {
      panel.append(el("div", { className: "card warn" },
        el("div", { className: "msg", textContent: `Your other tab "${x.other_title || x.other_origin}" has a different ${x.semantic}${x.other_tail ? ` (ends ${x.other_tail})` : ""}.` }),
        el("div", { className: "tag", textContent: "Open-tab context · compared in this browser only" })));
    }
    if (rules.length) {
      panel.append(el("h4", { textContent: `Rules for this task (${(S.task || "other").replaceAll("_", " ")})` }));
      for (const r of rules) panel.append(el("div", { className: "card" }, el("div", { textContent: r.message }), el("div", { className: "tag", textContent: ruleTag(r) })));
    }
    if (ctx.length) {
      panel.append(el("h4", { textContent: "From past sessions" }));
      for (const c of ctx) panel.append(el("div", { className: "card" }, el("div", { textContent: c.fact }), el("div", { className: "tag", textContent: `${c.source} · ${c.date} · ${c.why}` })));
    }
    if (tm.length) {
      panel.append(el("h4", { textContent: "Matches open tab" }));
      for (const t of tm) for (const s of t.sessions) panel.append(el("div", { className: "card" },
        el("div", { textContent: s.fact }),
        el("div", { className: "tag", textContent: `Matches open tab: ${t.title || t.origin} · ${s.date}` })));
    }
    const d = S.res && S.res.ok ? S.res.data : null;
    panel.append(el("div", { className: "foot", textContent: d ? `${d.source.label}${d.version ? ` · ${d.version}` : ""} · recall: ${d.recall}${S.res.live ? "" : " · backend offline, cached rules"}` : `Backend unavailable: ${S.error || (S.res && S.res.error) || "unknown"}` }));
    layer.append(panel);
  }

  // ------------------------------------------------------------------ evaluation
  async function evaluateAll() {
    const rules = rulesNow();
    const next = new Map();
    for (const f of S.fields) {
      if (!f.el.isConnected) continue;
      for (const rule of rules) {
        const hit = await M.evaluate(rule, fieldState(f));
        if (hit) next.set(keyOf(rule.id, f), { el: f.el, hit, rule, dismiss: dismissKey(rule.id, f) });
      }
    }
    for (const [k, c] of next) if (!S.shown.has(k + c.dismiss)) { S.shown.add(k + c.dismiss); notify(c.rule.id, "shown"); }
    S.conflicts = next;
    if (prefs.cross_tab) {
      const facts = [];
      for (const f of S.fields) {
        if (!/^(phone|email|city)$/.test(f.semantic)) continue;
        const v = M.normalize(f.semantic, f.el.value);
        facts.push({ semantic: f.semantic, hash: v ? await M.sha256Hex(`${M.SALT}${f.semantic}:${v}`) : "", tail: f.semantic === "phone" ? v.slice(-4) : "" });
      }
      const r = await send({ type: "observe", task: S.task, fields: facts });
      S.cross = r && r.ok ? r.conflicts : [];
    }
    render();
  }

  let sigs = "";
  async function poll(force) {
    const sig = S.fields.map((f) => `${f.el.value}|${f.el.checked}`).join("\u0001");
    if (!force && sig === sigs) { if (openConflicts(false).length) render(); return; }
    sigs = sig;
    try { await evaluateAll(); } catch (e) { S.error = `check failed: ${e && e.message || e}`; render(); }
  }

  async function scan() {
    const pr = await send({ type: "settings" });
    if (pr && pr.ok) Object.assign(prefs, { hold_submit: pr.hold_submit, cross_tab: pr.cross_tab, paused: pr.paused });
    if (prefs.paused) { layer.textContent = ""; return; }
    sniffTerminal();
    S.fields = terminal ? [] : D.collect(document).filter((f) => visible(f.el));
    const { task } = T.classify(vocab, document, S.fields);
    if (task !== S.task) {
      S.task = task;
      S.res = await send({ type: "assist", task });
      if (!S.res.ok) S.error = S.res.error;
    }
    await poll(true);
  }
  const refresh = () => poll(true);

  // ------------------------------------------------------------------ submit hold (optional, once per attempt)
  function shouldHold() { return !terminal && !prefs.paused && prefs.hold_submit && !S.bypass && (openConflicts(true).length + S.cross.length) > 0; }
  function hold(e, pending) { e.preventDefault(); e.stopImmediatePropagation(); S.pending = pending; S.panelOpen = true; render(); }
  function releaseSubmit() {
    const p = S.pending;
    S.pending = null; S.panelOpen = false; S.bypass = true;
    setTimeout(() => { S.bypass = false; }, 1500);
    render();
    if (!p) return;
    if (p.kind === "submit" && p.form.isConnected) p.form.requestSubmit(p.submitter && p.submitter.isConnected ? p.submitter : undefined);
    else if (p.kind === "click" && p.el.isConnected) p.el.click();
  }
  const submitTarget = (t) => t && t.closest && t.closest("button, input[type=submit], input[type=button], [role=button]");
  // Re-check just before the click lands, so a value set by script a moment ago is evaluated.
  window.addEventListener("pointerdown", (e) => { const b = submitTarget(e.target); if (b && D.isSubmit(b)) poll(false); }, true);
  window.addEventListener("click", (e) => {
    if (!e.isTrusted && S.bypass) return;
    const b = submitTarget(e.target);
    if (b && D.isSubmit(b) && shouldHold()) hold(e, { kind: "click", el: b });
  }, true);
  window.addEventListener("submit", (e) => { if (shouldHold()) hold(e, { kind: "submit", form: e.target, submitter: e.submitter }); }, true);

  // ------------------------------------------------------------------ wiring
  let mo = 0;
  new MutationObserver(() => { clearTimeout(mo); mo = setTimeout(scan, 400); }).observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener("input", () => poll(false), true);
  document.addEventListener("change", () => poll(false), true);
  let raf = 0;
  const reflow = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; if (openConflicts(false).length) render(); }); };
  window.addEventListener("scroll", reflow, true);
  window.addEventListener("resize", reflow);
  setInterval(() => poll(false), 800);
  chrome.runtime.onMessage.addListener((msg, _s, reply) => {
    if (msg && msg.type === "state") reply({ task: S.task || "other", rules: rulesNow().length, conflicts: openConflicts(true).length + S.cross.length });
  });
  await scan();
})();
