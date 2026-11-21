// Assist eval (PLAN phase 5): hand-labeled form states on the live-captured Luma and Vouch fixtures and on
// synthetic pages. Runs the shipped detector, task classifier and matcher (jsdom, no browser) against an eval rule
// set shaped like promoted rules, and reports precision and recall per rule. Fails when precision < 1.0: a false
// warning costs more trust than a missed one, and the plan requires precision 1.0 before default-on.
//   node proofloop/extension/test/assist_eval.cjs [--json]
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const ext = path.resolve(__dirname, '..');
const D = require(path.join(ext, 'assist/detect.js'));
const M = require(path.join(ext, 'assist/match.js'));
const T = require(path.join(ext, 'assist/task.js'));
const vocab = JSON.parse(fs.readFileSync(path.resolve(ext, '../schemas/tasks.json'), 'utf8'));
const { cases } = JSON.parse(fs.readFileSync(path.join(__dirname, 'eval/cases.json'), 'utf8'));
const pages = JSON.parse(fs.readFileSync(path.join(__dirname, 'eval/pages.json'), 'utf8'));
const VALUES = { '[PHONE-FAMILY]': '415-555-0100', '[PHONE-PRO]': '415-555-0142' };

// Eval rule set: the kinds the mutator can produce, grounded in real sessions. Served the way page_assist.py serves
// them (forbidden values hashed); this file hashes with the same normalization (parity is tested in test_assist.cjs).
const RULES = [
  { id: 'city-not-san-jose', kind: 'forbid_value', field: 'city', forbid: ['San Jose'], tasks: ['event_registration', 'insurance_or_service_quote'], message: 'm' },
  { id: 'phone-professional', kind: 'forbid_value', field: 'phone', forbid: ['[PHONE-FAMILY]'], tasks: ['job_application', 'insurance_or_service_quote'], message: 'm' },
  { id: 'no-sponsor-consent', kind: 'keep_unchecked', label_all: ['sponsor'], tasks: ['event_registration'], message: 'm' },
  { id: 'ask-work-type', kind: 'confirm_choice', label_any: ['work type'], tasks: ['job_application'], message: 'm' },
];
async function served(rule) {
  const out = { id: rule.id, kind: rule.kind, tasks: rule.tasks, message: rule.message };
  if (rule.kind === 'forbid_value') {
    out.field = rule.field;
    out.forbid = [];
    for (const t of rule.forbid) out.forbid.push({ sha256: await M.sha256Hex(`${M.SALT}${rule.field}:${M.normalize(rule.field, VALUES[t] || t)}`), label: t });
  } else { out.terms = rule.label_all || rule.label_any; out.match = rule.label_all ? 'all' : 'any'; }
  return out;
}

function load(page) {
  if (page === 'luma' || page === 'vouch') {
    const f = page === 'luma' ? 'luma_registration.html' : 'vouch_apply.html';
    return new JSDOM(fs.readFileSync(path.join(__dirname, 'fixtures', f), 'utf8'), { url: page === 'luma' ? 'https://luma.com/personalagenthack' : 'https://apply.vouch.us/' }).window.document;
  }
  return new JSDOM(`<!doctype html><title>${page}</title><body>${pages[page].html}</body>`, { url: pages[page].url }).window.document;
}

function apply(doc, [sel, v]) {
  const el = sel.startsWith('checkbox:') ? doc.querySelectorAll('input[type=checkbox]')[Number(sel.slice(9))] : doc.querySelector(sel);
  if (!el) throw new Error(`no element ${sel}`);
  if (typeof v === 'boolean') el.checked = v; else el.value = v;
}

(async () => {
  const rules = await Promise.all(RULES.map(served));
  const per = Object.fromEntries(RULES.map((r) => [r.id, { tp: 0, fp: 0, fn: 0 }]));
  const wrong = [];
  for (const c of cases) {
    const doc = load(c.page);
    for (const s of c.set) apply(doc, s);
    const fields = D.collect(doc);
    const { task } = T.classify(vocab, doc, fields);
    const fired = new Set();
    for (const f of fields) for (const r of rules) {
      if (!r.tasks.includes(task)) continue;
      if (await M.evaluate(r, { semantic: f.semantic, label: f.label, value: f.el.value, checked: !!f.el.checked })) fired.add(r.id);
    }
    const want = new Set(c.expect);
    for (const id of Object.keys(per)) {
      if (fired.has(id) && want.has(id)) per[id].tp++;
      else if (fired.has(id)) { per[id].fp++; wrong.push(`${c.id}: false warning ${id} (task ${task})`); }
      else if (want.has(id)) { per[id].fn++; wrong.push(`${c.id}: missed ${id} (task ${task})`); }
    }
  }
  const sum = Object.values(per).reduce((a, b) => ({ tp: a.tp + b.tp, fp: a.fp + b.fp, fn: a.fn + b.fn }), { tp: 0, fp: 0, fn: 0 });
  const p = (x) => (x.tp + x.fp ? x.tp / (x.tp + x.fp) : 1), r = (x) => (x.tp + x.fn ? x.tp / (x.tp + x.fn) : 1);
  const report = { cases: cases.length, precision: +p(sum).toFixed(3), recall: +r(sum).toFixed(3), per_rule: Object.fromEntries(Object.entries(per).map(([k, v]) => [k, { ...v, precision: +p(v).toFixed(3), recall: +r(v).toFixed(3) }])), errors: wrong };
  if (process.argv.includes('--json')) console.log(JSON.stringify(report, null, 1));
  else {
    console.log(`assist eval: ${cases.length} labeled form states, precision ${report.precision}, recall ${report.recall}`);
    for (const [k, v] of Object.entries(report.per_rule)) console.log(`  ${k.padEnd(20)} tp ${v.tp} fp ${v.fp} fn ${v.fn}  precision ${v.precision} recall ${v.recall}`);
    for (const w of wrong) console.log('  ' + w);
  }
  if (report.precision < 1) process.exitCode = 1;
})().catch((e) => { console.error(e); process.exit(1); });
