// Field classifier. Decides whether a form control is a city or a single-line address field from its
// label, autocomplete, name and placeholder. Pure functions over DOM nodes; no network, no storage.
(function (root) {
  const clean = (s) => (s || "").replace(/[\u00a0\u200b]/g, " ").replace(/\*/g, " ").replace(/\s+/g, " ").trim();

  function eligible(el) {
    if (!el || !el.tagName) return false;
    const tag = el.tagName.toLowerCase();
    if (tag === "textarea") return false;
    if (tag !== "input") return false;
    const type = (el.getAttribute("type") || "text").toLowerCase();
    return type === "text" || type === "search";
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

  // Returns { semantic: "city"|"address", label, score } or null.
  function classify(el) {
    if (!eligible(el)) return null;
    const label = labelText(el);
    const ac = (el.getAttribute("autocomplete") || "").toLowerCase();
    const ph = clean(el.getAttribute("placeholder"));
    const name = `${el.getAttribute("name") || ""} ${el.id || ""}`;
    let city = 0, address = 0;
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

  function collect(scope) {
    const out = [];
    for (const el of scope.querySelectorAll("input")) {
      const c = classify(el);
      if (c) out.push({ el, ...c });
    }
    return out;
  }

  const api = { classify, collect, labelText };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ProofLoopDetect = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
