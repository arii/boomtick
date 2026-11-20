// Deterministic matcher. Given a card, a field semantic and the value the user typed, decide whether the
// value breaks the card, and what the corrected value would be. No network calls: this runs on every edit.
(function (root) {
  const STATE = "(?:[a-z]{2}|california)";
  const norm = (s) => String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/\./g, "").replace(/\s+/g, " ").trim();
  const trimState = (s) => s.replace(new RegExp(`\\s+${STATE}$`), "").trim();
  const stateSegment = new RegExp(`^${STATE}(?:\\s+\\d{5}(?:-\\d{4})?)?$`);
  const COUNTRY = /^(usa?|united states(?: of america)?)$/;

  function forbidden(card, city) {
    const c = trimState(norm(city));
    return card.forbid.map(norm).includes(c);
  }

  function cityFieldMatch(card, value) {
    const parts = value.split(",");
    const first = parts[0];
    if (!forbidden(card, first)) return null;
    const suffix = norm(first).match(new RegExp(`\\s+(${STATE})$`));
    const lead = suffix ? first.trim().slice(first.trim().length - suffix[1].length) : "";
    parts[0] = card.expect + (lead ? ` ${lead}` : "");
    return { found: first.trim(), replacement: parts.join(",").replace(/^\s+/, "") };
  }

  function addressFieldMatch(card, value) {
    const segs = value.split(",").map((s) => s.trim());
    if (segs.length >= 2) {
      let idx = -1;
      for (let i = 1; i < segs.length; i++) if (stateSegment.test(norm(segs[i]))) { idx = i - 1; break; }
      if (idx < 0) {
        let last = segs.length - 1;
        if (COUNTRY.test(norm(segs[last]))) last--;
        if (last >= 1) idx = last;
      }
      if (idx >= 0 && forbidden(card, segs[idx])) {
        const out = segs.slice();
        out[idx] = card.expect;
        return { found: segs[idx], replacement: out.join(", ") };
      }
      return null;
    }
    // No commas: "123 Main St San Jose CA 95112". The city must be followed by a state and nothing else.
    for (const bad of card.forbid.map(norm)) {
      const re = new RegExp(`\\b${bad}\\s+${STATE}(?:\\s+\\d{5}(?:-\\d{4})?)?\\s*$`, "i");
      const hit = norm(value).match(re);
      if (hit) {
        const rx = new RegExp(`${bad.split(" ").join("\\s+")}(?=\\s+${STATE}(?:\\s+\\d{5}(?:-\\d{4})?)?\\s*$)`, "i");
        const alt = value.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        if (rx.test(alt)) return { found: bad, replacement: alt.replace(rx, card.expect) };
      }
    }
    return null;
  }

  // Returns null or { card_id, found, expect, replacement, message }.
  function evaluate(card, semantic, value) {
    if (!card || card.kind !== "forbid_value" || card.field.semantic !== semantic) return null;
    const v = String(value || "").trim();
    if (!v) return null;
    const hit = semantic === "city" ? cityFieldMatch(card, v) : addressFieldMatch(card, v);
    if (!hit) return null;
    return { card_id: card.id, found: hit.found, expect: card.expect, replacement: hit.replacement, message: card.message };
  }

  const api = { evaluate, norm };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ProofLoopMatch = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
