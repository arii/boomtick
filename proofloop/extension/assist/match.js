// fallow-ignore-file unused-file
// Reason: content script loaded via chrome.scripting from background.js SCRIPTS, not via import.
// Conflict matcher (observer). Rules arrive from the backend with forbidden values as salted SHA-256
// hashes (harness/page_assist.py). This file normalizes what is in a field the same way, hashes the
// candidate spans and compares. No network, no storage; values never leave this function.
(function (root) {
  const SALT = "proofloop:v1:";
  // A US state as it appears after normalization: "ca", "california", or "us ca" (from "US-CA").
  const STATE = "(?:(?:us )?[a-z]{2}|california)";

  function normalize(field, value) {
    const v = String(value == null ? "" : value);
    if (field === "phone") {
      const d = v.replace(/\D/g, "");
      return d.length === 11 && d.startsWith("1") ? d.slice(1) : d;
    }
    return v.normalize("NFD").replace(/[^\x00-\x7f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
  }

  // Spans of a field value that could be the rule's field. City rules also look inside single-line addresses.
  function candidates(ruleField, semantic, value) {
    const out = new Set();
    if (ruleField === "phone" || ruleField === "email") {
      if (semantic === ruleField) out.add(normalize(ruleField, value));
      return [...out].filter(Boolean);
    }
    if (ruleField !== "city" && ruleField !== "address") return [];
    if (semantic !== "city" && semantic !== "address") return [];
    const segs = String(value).split(",").map((s) => normalize("city", s)).filter(Boolean);
    const trimState = (s) => s.replace(new RegExp(`\\s+${STATE}(?:\\s+\\d{5}(?:\\s+\\d{4})?)?$`), "").trim();
    if (semantic === "city") {
      if (segs[0]) { out.add(segs[0]); out.add(trimState(segs[0])); }
      out.add(normalize("city", value));
    } else if (segs.length >= 2) {
      const stateLike = new RegExp(`^${STATE}(?:\\s+\\d{5}(?:\\s+\\d{4})?)?$|^\\d{5}(?:\\s+\\d{4})?$`);
      for (let i = 1; i < segs.length; i++) { out.add(segs[i]); out.add(trimState(segs[i])); }
      // "S Main St San Jose, US-CA 95035": the city ends the segment before a state or zip segment.
      for (let i = 0; i < segs.length - 1; i++) {
        if (!stateLike.test(segs[i + 1])) continue;
        const w = segs[i].split(" ");
        for (let n = 1; n <= 3 && n < w.length; n++) out.add(w.slice(-n).join(" "));
      }
    } else if (segs.length === 1) {
      // "123 Main St San Jose CA 95112": only when a state (and optional zip) ends the value.
      const m = segs[0].match(new RegExp(`^(.*\\S)\\s+${STATE}(?:\\s+\\d{5}(?:\\s+\\d{4})?)?$`));
      if (m) { const w = m[1].split(" "); for (let n = 1; n <= 3 && n < w.length; n++) out.add(w.slice(-n).join(" ")); }
    }
    return [...out].filter(Boolean);
  }

  // SHA-256. crypto.subtle exists only in secure contexts (not on http:// pages), so a small FIPS 180-4
  // implementation is used when it is missing. Both give identical hex digests (tested against Python).
  const K = new Uint32Array([0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01,
    0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa,
    0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138,
    0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624,
    0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f,
    0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]);
  function sha256Sync(bytes) {
    const len = bytes.length, padded = new Uint8Array(((len + 9 + 63) >> 6) << 6);
    padded.set(bytes); padded[len] = 0x80;
    const dv = new DataView(padded.buffer);
    dv.setUint32(padded.length - 8, Math.floor((len * 8) / 0x100000000)); dv.setUint32(padded.length - 4, (len * 8) >>> 0);
    const H = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
    const w = new Uint32Array(64);
    const rot = (x, n) => (x >>> n) | (x << (32 - n));
    for (let off = 0; off < padded.length; off += 64) {
      for (let i = 0; i < 16; i++) w[i] = dv.getUint32(off + i * 4);
      for (let i = 16; i < 64; i++) {
        const s0 = rot(w[i - 15], 7) ^ rot(w[i - 15], 18) ^ (w[i - 15] >>> 3), s1 = rot(w[i - 2], 17) ^ rot(w[i - 2], 19) ^ (w[i - 2] >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
      }
      let [a, b, c, d, e, f, g, h] = H;
      for (let i = 0; i < 64; i++) {
        const t1 = (h + (rot(e, 6) ^ rot(e, 11) ^ rot(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i]) >>> 0;
        const t2 = ((rot(a, 2) ^ rot(a, 13) ^ rot(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) >>> 0;
        h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
      }
      H[0] += a; H[1] += b; H[2] += c; H[3] += d; H[4] += e; H[5] += f; H[6] += g; H[7] += h;
    }
    return [...H].map((x) => x.toString(16).padStart(8, "0")).join("");
  }
  async function sha256Hex(text) {
    const bytes = new TextEncoder().encode(text);
    if (globalThis.crypto && crypto.subtle) {
      const buf = await crypto.subtle.digest("SHA-256", bytes);
      return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
    }
    return sha256Sync(bytes);
  }

  const hasTerms = (label, terms, mode) => {
    const l = normalize("text", label);
    const t = terms.map((x) => normalize("text", x)).filter(Boolean);
    return mode === "all" ? t.every((x) => l.includes(x)) : t.some((x) => l.includes(x));
  };

  // field: { semantic, label, value, checked }. Returns null or { rule_id, kind, message, found }.
  async function evaluate(rule, field) {
    if (!rule || !field) return null;
    if (rule.kind === "keep_unchecked") {
      return field.semantic === "checkbox" && field.checked && hasTerms(field.label, rule.terms || [], "all")
        ? { rule_id: rule.id, kind: rule.kind, message: rule.message } : null;
    }
    if (rule.kind === "confirm_choice") {
      const filled = field.semantic === "radio" ? field.checked : String(field.value || "").trim() !== "";
      return filled && hasTerms(field.label, rule.terms || [], "any") ? { rule_id: rule.id, kind: rule.kind, message: rule.message, atSubmit: true } : null;
    }
    if (rule.kind !== "forbid_value") return null;
    const spans = candidates(rule.field, field.semantic, field.value || "");
    if (!spans.length) return null;
    const wanted = new Map((rule.forbid || []).filter((f) => f && f.sha256).map((f) => [f.sha256, f.label]));
    for (const s of spans) {
      const h = await sha256Hex(`${SALT}${rule.field}:${s}`);
      if (wanted.has(h)) return { rule_id: rule.id, kind: rule.kind, message: rule.message, found: wanted.get(h), expect: rule.expect_label };
    }
    return null;
  }

  const api = { evaluate, normalize, candidates, sha256Hex, sha256Sync, SALT };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ProofLoopMatch = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
