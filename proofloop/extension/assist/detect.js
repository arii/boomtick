// Field classifier for the pre-submit review (PLAN.md 4.0, 4.1). Classifies form controls as city, single-line
// address, phone or labeled checkbox from label, autocomplete, type, name and placeholder, and finds the submit
// control. Pure functions over DOM nodes; no network, no storage. Which checkbox matters is decided by rule cards,
// not here: every labeled checkbox is reported with its label.
(function (root) {
  const clean = (s) => (s || "").replace(/[\u00a0\u200b]/g, " ").replace(/\*/g, " ").replace(/\s+/g, " ").trim();

  function eligible(el) {
    if (!el || !el.tagName) return false;
    const tag = el.tagName.toLowerCase();
    if (tag === "textarea") return false;
    if (tag !== "input") return false;
    const type = (el.getAttribute("type") || "text").toLowerCase();
    return type === "text" || type === "search" || type === "tel";
  }

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

  const CITY_LABEL = /\bcity\b|\btown\b|\bbased in\b|\bwhere (do you live|are you (based|located))\b/i;
  const ADDRESS_TEXT = /\b(street|mailing|home|full)?\s*address\b|\bzip( code)?\b|\bpostal\b/i;
  const NOT_ADDRESS = /e-?mail|\bip\b|\burl\b|\bweb(site)?\b/i;
  const NAME_CITY = /(^|[._\-\[\s])(city|town|locality)($|[._\-\]\s])/i;

  const PHONE_LABEL = /\b(phone|mobile|cell)( number)?\b|\btelephone\b/i;

  function checkboxLabel(el) {
    let label = labelText(el);
    if (!label) {
      // Custom checkboxes sometimes put the text in a sibling of the input's wrapper instead of a <label>.
      let p = el.parentElement;
      for (let i = 0; i < 3 && p && !label; i++, p = p.parentElement) label = clean(p.textContent);
    }
    return label.slice(0, 300);
  }

  // Returns { semantic: "city"|"address"|"phone"|"checkbox", label, score } or null.
  function classify(el) {
    if (el && el.tagName === "INPUT" && (el.getAttribute("type") || "").toLowerCase() === "checkbox") {
      const label = checkboxLabel(el);
      return label ? { semantic: "checkbox", label, score: 5 } : null;
    }
    if (!eligible(el)) return null;
    const label = labelText(el);
    const ac = (el.getAttribute("autocomplete") || "").toLowerCase();
    const ph = clean(el.getAttribute("placeholder"));
    const name = `${el.getAttribute("name") || ""} ${el.id || ""}`;
    let city = 0, address = 0, phone = 0;
    if ((el.getAttribute("type") || "").toLowerCase() === "tel") phone += 8;
    if (/^tel(-national)?$/.test(ac)) phone += 10;
    if (PHONE_LABEL.test(label)) phone += 6;
    if (/(^|[._\-\[\s])(phone|mobile|tel)($|[._\-\]\s])/i.test(name)) phone += 5;
    if (phone >= 5 && !/e-?mail/i.test(label)) return { semantic: "phone", label: label || ph, score: phone };
    if (/address-level2/.test(ac)) city += 10;
    if (/street-address|address-line|postal-code/.test(ac)) address += 8;
    if (CITY_LABEL.test(label)) city += 6;
    if (NAME_CITY.test(name)) city += 5;
    if (ph.length <= 24 && /^(your )?(city|town)\b/i.test(ph)) city += 5;
    for (const text of [label, ph]) if (ADDRESS_TEXT.test(text) && !NOT_ADDRESS.test(text)) address += 6;
    if (address >= 5 && address >= city) return { semantic: "address", label: label || ph, score: address };
    if (city >= 5) return { semantic: "city", label: label || ph, score: city };
    return null;
  }

  const SUBMIT_TEXT = /^(submit( application)?|apply( now)?|send( application)?|request to join|register|rsvp|start application|join( event)?|complete registration)$/i;

  // Submit controls in scope: type=submit buttons and inputs, plus buttons whose text is submit wording
  // (Vouch's "Start Application" is type=button).
  function submitControls(scope) {
    const out = [];
    for (const b of scope.querySelectorAll("button, input[type=submit], [role=button]")) {
      const type = (b.getAttribute("type") || (b.tagName === "BUTTON" ? "submit" : "")).toLowerCase();
      const text = clean(b.tagName === "INPUT" ? b.value : b.textContent);
      const inForm = !!b.closest("form");
      if ((type === "submit" && inForm && b.tagName !== "DIV") || SUBMIT_TEXT.test(text)) out.push({ el: b, text });
    }
    return out;
  }

  function collect(scope) {
    const out = [];
    for (const el of scope.querySelectorAll("input")) {
      const c = classify(el);
      if (c) out.push({ el, ...c });
    }
    return out;
  }

  const api = { classify, collect, labelText, submitControls };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ProofLoopDetect = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
