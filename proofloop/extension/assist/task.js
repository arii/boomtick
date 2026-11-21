// Task classifier (local). Scores the page against the task vocabulary served by the backend
// (schemas/tasks.json, GET /tasks) using the title, path words, headings, buttons, short helper text and field
// types. Multi-word phrases score 2 points per word.
// Page text is read here and never sent anywhere; only the winning task id leaves this script.
(function (root) {
  const norm = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9\s-]+/g, " ").replace(/\s+/g, " ").trim();

  function signals(doc, fields) {
    const bits = [doc.title, doc.location ? doc.location.pathname.replace(/[\/_-]+/g, " ") : ""];
    for (const h of doc.querySelectorAll("h1, h2, h3, legend, [role=dialog] [class*=title]")) bits.push(h.textContent);
    for (const b of doc.querySelectorAll("button, [role=button], input[type=submit]")) bits.push(b.textContent || b.value);
    for (const f of fields) bits.push(f.label);
    // Short helper text inside forms and dialogs ("the business you want to insure").
    for (const p of doc.querySelectorAll("form p, form small, [role=dialog] p, [id$=helper-text], [id$=-desc]")) {
      const t = p.textContent || "";
      if (t.length <= 200) bits.push(t);
    }
    return { text: ` ${norm(bits.join(" ").slice(0, 20000))} `, semantics: new Set(fields.map((f) => f.semantic)) };
  }

  // Returns { task, score, scores }. "other" unless a task has at least 2 points and a form is present.
  function classify(vocab, doc, fields) {
    const sig = signals(doc, fields);
    const scores = {};
    for (const t of vocab.tasks || []) {
      let s = 0;
      // Longer phrases are more specific: 2 points per word.
      for (const phrase of t.signals.text || []) { const p = norm(phrase); if (sig.text.includes(` ${p} `)) s += 2 * p.split(" ").length; }
      for (const f of t.signals.fields || []) if (sig.semantics.has(f)) s += 1;
      scores[t.id] = s;
    }
    let best = "other", top = 0;
    for (const [id, s] of Object.entries(scores)) if (s > top) { best = id; top = s; }
    return { task: top >= 2 && fields.length > 0 ? best : "other", score: top, scores };
  }

  const api = { classify, signals };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ProofLoopTask = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
