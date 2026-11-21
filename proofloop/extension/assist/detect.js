// Field detector (observer). Reports every labeled form control with a semantic type, and finds submit
// controls. Pure functions over DOM nodes; no network, no storage, never changes the page.
//   semantic: city | address | phone | email | checkbox | radio | choice | text
(function (root) {
  const clean = (s) => (s || "").replace(/[\u00a0\u200b]/g, " ").replace(/\*/g, " ").replace(/\s+/g, " ").trim();

  function labelText(el) {
    const doc = el.ownerDocument;
    const parts = [];
    if (el.labels) for (const l of el.labels) parts.push(l.textContent);
    const by = el.getAttribute("aria-labelledby");
    if (by) for (const id of by.split(/\s+/)) { const n = doc.getElementById(id); if (n) parts.push(n.textContent); }
    const al = el.getAttribute("aria-label");
    if (al) parts.push(al);
    return clean(parts.join(" "));
  }

  function groupLabel(el) {
    const fs = el.closest("fieldset");
    const lg = fs && fs.querySelector("legend");
    if (lg) return clean(lg.textContent);
    const g = el.closest("[role=radiogroup]");
    if (g) return clean(g.getAttribute("aria-label") || (g.getAttribute("aria-labelledby") && el.ownerDocument.getElementById(g.getAttribute("aria-labelledby"))?.textContent) || "");
    return "";
  }

  function nearbyText(el) {
    let p = el.parentElement;
    for (let i = 0; i < 3 && p; i++, p = p.parentElement) { const t = clean(p.textContent); if (t) return t.slice(0, 300); }
    return "";
  }

  const CITY_LABEL = /\bcity\b|\btown\b|\bbased in\b|\bwhere (do you live|are you (based|located))\b/i;
  const ADDRESS_TEXT = /\b(street|mailing|home|full)?\s*address\b|\bzip( code)?\b|\bpostal\b/i;
  const NOT_ADDRESS = /e-?mail|\bip\b|\burl\b|\bweb(site)?\b/i;
  const NAME_CITY = /(^|[._\-\[\s])(city|town|locality)($|[._\-\]\s])/i;
  const PHONE_LABEL = /\b(phone|mobile|cell)( number)?\b|\btelephone\b/i;
  const TEXTLIKE = new Set(["text", "search", "tel", "email", ""]);

  function textSemantic(el, label) {
    const ac = (el.getAttribute("autocomplete") || "").toLowerCase();
    const ph = clean(el.getAttribute("placeholder"));
    const name = `${el.getAttribute("name") || ""} ${el.id || ""}`;
    const type = (el.getAttribute("type") || "text").toLowerCase();
    let city = 0, address = 0, phone = 0, email = 0;
    if (type === "tel") phone += 8;
    if (/^tel(-national)?$/.test(ac)) phone += 10;
    if (PHONE_LABEL.test(label)) phone += 6;
    if (/(^|[._\-\[\s])(phone|mobile|tel)($|[._\-\]\s])/i.test(name)) phone += 5;
    if (type === "email" || ac === "email") email += 10;
    if (/\be-?mail\b/i.test(label) || /\be-?mail\b/i.test(name)) email += 6;
    if (/address-level2/.test(ac)) city += 10;
    if (/street-address|address-line|postal-code/.test(ac)) address += 8;
    if (CITY_LABEL.test(label)) city += 6;
    if (NAME_CITY.test(name)) city += 5;
    if (ph.length <= 24 && /^(your )?(city|town)\b/i.test(ph)) city += 5;
    for (const text of [label, ph]) if (ADDRESS_TEXT.test(text) && !NOT_ADDRESS.test(text)) address += 6;
    if (email >= 5 && email >= phone) return "email";
    if (phone >= 5) return "phone";
    if (address >= 5 && address >= city) return "address";
    if (city >= 5) return "city";
    return "text";
  }

  // Returns { semantic, label } or null for controls the observer ignores.
  function classify(el) {
    if (!el || !el.tagName) return null;
    const tag = el.tagName.toLowerCase();
    if (el.disabled || el.type === "hidden" || el.type === "password") return null;
    if (tag === "select") { const l = labelText(el); return l ? { semantic: "choice", label: l } : null; }
    if (tag === "textarea") { const l = labelText(el); return l ? { semantic: "text", label: l } : null; }
    if (tag !== "input") return null;
    const type = (el.getAttribute("type") || "text").toLowerCase();
    if (type === "checkbox") { const l = labelText(el) || nearbyText(el); return l ? { semantic: "checkbox", label: l.slice(0, 300) } : null; }
    if (type === "radio") { const l = labelText(el) || nearbyText(el); const g = groupLabel(el); return l || g ? { semantic: "radio", label: clean(`${g} ${l}`).slice(0, 300) } : null; }
    if (!TEXTLIKE.has(type)) return null;
    const label = labelText(el) || clean(el.getAttribute("placeholder"));
    const semantic = textSemantic(el, label);
    if (!label && semantic === "text") return null;
    return { semantic: el.getAttribute("role") === "combobox" && semantic === "text" ? "choice" : semantic, label };
  }

  function collect(scope) {
    const out = [];
    for (const el of scope.querySelectorAll("input, select, textarea")) { const c = classify(el); if (c) out.push({ el, ...c }); }
    return out;
  }

  // Words on a submit control. A form's plain <button> submits; outside a form only submit wording counts.
  const SUBMIT_TEXT = /^(submit( application)?|apply( now)?|send( application)?|request to join|register( now)?|rsvp|start application|join( event)?|complete registration|book( now)?|confirm( booking)?|sign up|create account)$/i;
  function isSubmit(b) {
    if (!b || !b.tagName) return false;
    const tag = b.tagName;
    if (tag !== "BUTTON" && !(tag === "INPUT" && /^(submit|button)$/i.test(b.type)) && b.getAttribute("role") !== "button") return false;
    const type = (b.getAttribute("type") || (tag === "BUTTON" ? "submit" : "")).toLowerCase();
    const text = clean(tag === "INPUT" ? b.value : b.textContent);
    return (type === "submit" && !!b.closest("form") && tag !== "DIV") || SUBMIT_TEXT.test(text);
  }
  function submitControls(scope) {
    return [...scope.querySelectorAll("button, input[type=submit], input[type=button], [role=button]")].filter(isSubmit)
      .map((el) => ({ el, text: clean(el.tagName === "INPUT" ? el.value : el.textContent) }));
  }

  const api = { classify, collect, labelText, submitControls, isSubmit, clean };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ProofLoopDetect = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
