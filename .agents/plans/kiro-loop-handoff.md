# Loop handoff: what to send Kiro when the Nebius loop promotes, and what Kiro will add

Status: ready. Nothing below is implemented until the bundle from a real promotion arrives (Gemini HOLD,
`kiro-assist-wire-gap.md`).

## 1. What to send (on the live machine)

```sh
cd /home/ari/boomtick/proofloop/harness
set -a && source ../../.env && set +a
python3 handoff.py > /tmp/proofloop-handoff.json                                   # always
PROOFLOOP_LIVE_SERVICES=senso python3 handoff.py --check-senso > /tmp/proofloop-handoff.json   # if Senso is reachable
```

`handoff.py` reads only what the loop wrote in `PROOFLOOP_STATE` and prints one JSON bundle. It contains no keys, no
private values (rules carry placeholders such as `[PHONE-FAMILY]`), no agent answers and no session text. It is safe to
paste into the Kiro session or commit under `.agents/plans/`. If there is no ledger it exits 2 with "nothing to hand
off".

Also say which model ran (`TWT_MODEL`) and whether `data/replay_tasks.json` was regenerated (PLAN 0.1).

## 2. Bundle shape

| Key | From | Used for |
|---|---|---|
| `active_version`, `promotions`, `statuses` | `proof_ledger.json` | Was there a real promotion; how many proposals were held, rejected or invalid |
| `ledger_entries[]` | every ledger entry: `cycle`, `timestamp`, `version`, `parent_version`, `status` (`baseline` \| `promoted` \| `held` \| `rejected` \| `invalid_proposal` \| `promotion_failed`), `gate` (`choice`, `reason`, `margin`, `train_gain`, `train_before/after`, `holdout_before/after`, `regressions`, `samples`), `scores` (`train`, `holdout`, per-task), `recall` (`mode`, `queries`), `llm.backend`, `rules_sha256`, `diff`, `evidence_sessions`, `senso` (`node_id`, `content_id`, `verified`, `title`) | Loop status for the page; checking the gate decisions are sane on real data |
| `active_rules` | `active_rules.json`: `rules` (the promoted rule set), `sha256`, `sha256_ok`, `scores`, `senso`, `promoted_at` | The real rules the page will serve |
| `last_run` | `last_run.json`: `generated`, `stop` (why the loop stopped), `active`, `services` | Loop status |
| `feedback` | `feedback.jsonl` counted per rule and action (`shown`, `dismissed`, `rule_wrong`) | Which feedback actions are actually used |
| `problems` | ledger schema check, rule-set re-validation (schema, grounding, hash) | Anything the backend would refuse |
| `senso_check` (with `--check-senso`) | `page_assist.source_tag` against the live node | Whether Senso readback works on real data. `senso` = confirmed; `senso-mismatch` with `reason` = `read failed (...)`, `node text is not the stored rule set JSON`, `node text is not a ProofLoop rule set`, or `hash differs from the local rule set` |

## 3. What Kiro does with it, in order

1. **Check the promotion is real.** `promotions >= 1`, the promoted entry has `gate.choice = promote` with
   `train_gain > margin`, `problems = []`, `active_rules.sha256_ok = true`. If not, report and stop.
2. **Senso readback.** If `senso_check.kind = senso`, done. If `read failed` or `not the stored rule set JSON`, the
   readback field names in `clients.SensoLive.read_text` are wrong: fix them against the real node response (Ari runs
   one `get_node` and pastes the key names, no content).
3. **Live page with the real rules.** Ari runs `node proofloop/extension/test/live_sites.cjs` (no `--test-rules`) on the
   live machine. Kiro checks the warnings it reports match `active_rules.rules.page_rules` for the page's task.
4. **Add only these `/assist` fields** (each backed by a bundle field above; nothing else from the Gemini spec):

| Field | Source | Why it is needed now |
|---|---|---|
| `active_skill_version` | `version` (alias kept) | The spec name, from a real promoted version |
| `senso_synced` (bool) | `source.kind == "senso"` (keep `source`) | The real Senso round trip exists |
| `loop_status.state` | `idle`, or `rolled_back` when the last ledger entry is `rejected` | Real ledger entries exist |
| `loop_status.last_gate_decision` | last ledger entry `gate.choice`, or `status` for `invalid_proposal`/`promotion_failed` | Same |
| `loop_status.last_delta` | last ledger entry `gate.train_gain` | Same |
| `loop_status.stop` | `last_run.stop` | Explains why the loop is idle |

   Not added until the data asks for it: `loop_status.state = running` (needs a loop heartbeat file; only if the
   bundle shows runs long enough to matter), `items[]` (a display layer; only if the real rule count makes the three
   current lists awkward), new feedback actions (only if `feedback` shows `dismissed` and `rule_wrong` are not enough).
   Never added without a separate security decision: full URLs, page titles of the active tab, `observed_value`, an
   `apply` action, the token in the request body.
5. **Tests first.** Each added field gets a server test fed from the bundle's real shape, and `pnpm run test:proofloop`
   stays green. Gate, ledger schema and task set are not changed.
