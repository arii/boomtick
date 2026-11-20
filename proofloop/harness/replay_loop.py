#!/usr/bin/env python3
"""ProofLoop replay harness.

Flow: ingest sessions -> Cognee recall -> replay tasks -> baseline replay ->
mutation -> local Replay Gate -> Senso promotion -> proof ledger -> rollback on reject.

    python3 replay_loop.py --reset                 # full demo run
    python3 replay_loop.py --reset --bad-demo      # plus a bad mutation that gets rolled back
    python3 replay_loop.py --status                # show which services are live vs stub
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

import agent
import clients
import replay_gate
import config
from atomic import atomic_write_json
import skill_prompt
import validate

BASE_SKILL = {"version": "v0", "steps": [agent.BASE_STEP]}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg=""):
    print(msg, flush=True)


# ------------------------------------------------------------- state
def load_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def save_json(path, obj):
    atomic_write_json(path, obj)


def state_paths():
    d = config.STATE_DIR
    return d / "active_skill.json", d / "proof_ledger.json", d / "last_run.json"


def reset_state():
    for f in config.STATE_DIR.glob("*.json"):
        if f.name != "keys.json":
            f.unlink()


# ------------------------------------------------------------- steps 1-2
def ingest_and_recall(sessions, suite):
    """Ingest into Cognee and check recall coverage. The replay suite always stays the full
    curated set, so pass rates are comparable run to run; partial recall is reported, not hidden."""
    if config.mode("cognee") == "live" and config.get("PROOFLOOP_ALLOW_SESSION_UPLOAD") != "1":
        raise SystemExit("Session upload disabled: authorize the specific input dataset before setting PROOFLOOP_ALLOW_SESSION_UPLOAD=1")
    cg = clients.cognee()
    log(f"[1] Cognee ingest via: {cg.label}")
    log(f"    {cg.ingest(sessions)}")
    kept, note = recall_tasks(cg, suite)
    if not kept and config.get("PROOFLOOP_INCLUDE_LOCAL_SKILLS") == "1":
        docs = [(p.name, p.read_text()) for p in sorted(config.SKILLS_LOCAL.glob("*.md"))]
        if docs:
            log(f"    recall empty; seeding graph with {len(docs)} local skill docs")
            cg.ingest(sessions, extra_docs=docs)
            kept, note = recall_tasks(cg, suite)
    total = len(suite["tasks"])
    if len(kept) < total:
        note += f"; WARNING partial recall, replaying the full {total}-task suite"
    return suite["tasks"], note, cg.label


def recall_tasks(cg, suite):
    """Keep tasks whose source session is returned by Cognee for the task's constraint."""
    kept = []
    for t in suite["tasks"]:
        hits = cg.search(t["expected_constraint"])
        ids = {sid for h in hits for sid in (h.get("session_ids") or [h.get("session_id")]) if sid}
        if t["source_session_id"] in ids:
            kept.append(t)
    return kept, f"{len(kept)}/{len(suite['tasks'])} tasks recalled from Cognee"


# ------------------------------------------------------------- mutation
def next_version(v):
    m = re.match(r"v1\.(\d+)", v)
    return f"v1.{int(m.group(1)) + 1}" if m else "v1.1"


def mutate(skill, rep):
    """Return (new_steps, how). Uses OpenRouter when keyed, else rule-based."""
    counts = {}
    for res in rep["results"]:
        for c in res["failed_checks"]:
            n = agent.check_name(c)
            counts[n] = counts.get(n, 0) + 1
    if not counts:
        return None, "no failures"
    if config.mode("llm") == "live":
        try:
            add = clients.llm_propose_steps(counts, agent.KNOWN_STEPS, skill["steps"])
            if add:
                return skill["steps"] + add, f"llm ({config.llm_backend()})"
        except clients.ApiError as e:
            log(f"    LLM mutation failed ({e}); falling back to rule-based mutator")
    add = []
    for c in sorted(counts, key=lambda c: (-counts[c], c)):
        step = agent.CHECK_FIX.get(c)
        if step and step not in skill["steps"] and step not in add:
            add.append(step)
        if len(add) == 2:
            break
    if not add:
        return None, "no applicable fix"
    return skill["steps"] + add, "rule-based (offline mutation)"


def bad_mutation(skill):
    """A regression: drop the grounding step."""
    steps = [s for s in skill["steps"] if s != "ground_in_related_tabs"]
    return steps if steps != skill["steps"] else skill["steps"][:-1]


def diff(old, new):
    out = [f"+ {s}" for s in new if s not in old] + [f"- {s}" for s in old if s not in new]
    return "\n".join(out) or "(no change)"


# ------------------------------------------------------------- one cycle
def run_cycle(n, active, steps, version, tasks, base_rep, ledger, senso_client):
    cand = {"version": version, "steps": steps}
    rep = agent.replay(cand, tasks)
    d = diff(active["steps"], steps)
    log(f"\n[4] Candidate {version}: {rep['passed']}/{rep['total']} passed "
        f"(active {active['version']}: {base_rep['passed']}/{base_rep['total']})")
    log("    diff:\n      " + d.replace("\n", "\n      "))
    for r in rep["results"]:
        if not r["passed"]:
            log(f"    - {r['task_id']} fails: {', '.join(r['failed_checks'])}")

    gate = replay_gate.decide(base_rep, rep, tasks)
    log(f"[5] Local Replay Gate: {gate['choice']} ({gate['reason']})")

    node_id = ""
    status = "held" if gate["choice"] == "hold" else "rolled_back"
    retrieval = {"verified": False, "mode": config.mode("senso")}
    proof = {"cycle": n, "version": version, "parent": active["version"],
             "pass_before": base_rep["passed"], "pass_after": rep["passed"], "total": rep["total"]}
    if gate["choice"] == "promote":
        cycle_id = f"cyc-{n:03d}"
        text = json.dumps({"skill": cand, "proof": proof, "replay_gate": gate, "promoted_at": now()}, indent=2)
        try:
            result = clients.senso_promote(senso_client, f"ProofLoop skill {version} {cycle_id} {now()}", text, f"{version}+{cycle_id}")
            if not result.get("verified"):
                raise clients.ApiError(0, "promotion readback not verified")
            retrieval = {**result, "mode": config.mode("senso")}
            node_id = retrieval["node_id"]
            status = "promoted"
            log(f"[6] {senso_client.label}: readback found content ({retrieval['mode']})")
        except clients.ApiError:
            status = "promotion_failed"
            log("[6] Promotion/readback failed; active skill unchanged. Remote content may remain.")
    else:
        log(f"[8] {status}: local Replay Gate returned {gate['choice']}; active stays {active['version']}")

    entry = {
        "cycle_id": f"cyc-{n:03d}", "timestamp": now(), "version": version,
        "parent_version": active["version"],
        "tasks_passed_before": base_rep["passed"], "tasks_passed_after": rep["passed"],
        "total_tasks": rep["total"], "pass_rate_before": base_rep["pass_rate"],
        "pass_rate_after": rep["pass_rate"], "delta": round(rep["pass_rate"] - base_rep["pass_rate"], 4),
        "skill_diff": d,
        "replay_gate": gate, "retrieval": retrieval,
        "senso_kb_node_id": node_id, "status": status,
    }
    ledger["entries"].append(entry)
    if status == "promoted":
        ledger["active_version"] = version
        active, base_rep = cand, rep
    log(f"[7] Ledger entry {entry['cycle_id']}: {version} {status}, delta {entry['delta']:+.2f}")
    return active, base_rep, rep


# ------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="clear state and start from v0")
    ap.add_argument("--bad-demo", action="store_true", help="after evolving, try a bad mutation (expect rollback)")
    ap.add_argument("--max-cycles", type=int, default=4)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--sync-prompt", metavar="PATH", help="write the active prompt into PATH between PROOFLOOP markers "
                    "(also PROOFLOOP_PROMPT_TARGET). Only .md/.mdc/.txt files; never .env or .git")
    ap.add_argument("--create-target", action="store_true", help="create the --sync-prompt file if it does not exist")
    args = ap.parse_args()

    if args.status:
        print(json.dumps(config.status(), indent=2))
        return 0
    if args.reset:
        reset_state()

    skill_p, ledger_p, run_p = state_paths()
    active = load_json(skill_p, BASE_SKILL)
    ledger = load_json(ledger_p, {"active_version": active["version"], "entries": []})
    if ledger.get("schema_version") != 2 and ledger.get("entries"):
        raise SystemExit("Legacy ledger: use a separate PROOFLOOP_STATE directory or explicitly --reset; no silent migration.")
    ledger["schema_version"] = 2

    sessions = validate.load_sessions()
    suite = validate.load_suite()
    log("Service modes: " + "; ".join(f"{k}={v['mode']}" for k, v in config.status().items()))

    tasks, recall_note, cognee_label = ingest_and_recall(sessions, suite)
    log(f"[2] {recall_note}")
    save_json(config.STATE_DIR / "replay_tasks.generated.json", {"suite_id": suite["suite_id"], "tasks": tasks})

    base_rep = agent.replay(active, tasks)
    log(f"[3] Baseline {active['version']}: {base_rep['passed']}/{base_rep['total']} passed")
    for r in base_rep["results"]:
        if not r["passed"]:
            log(f"    - {r['task_id']} fails: {', '.join(r['failed_checks'])}")
    initial = {"version": active["version"], "passed": base_rep["passed"], "total": base_rep["total"]}

    sc = clients.senso()
    n = len(ledger["entries"])
    cycles = []
    try:
        for _ in range(args.max_cycles):
            if base_rep["passed"] == base_rep["total"]:
                break
            steps, how = mutate(active, base_rep)
            if not steps:
                log(f"No further mutation available ({how}); stopping.")
                break
            n += 1
            log(f"\n--- cycle {n}: mutation via {how}")
            active, base_rep, rep = run_cycle(n, active, steps, next_version(active["version"]),
                                              tasks, base_rep, ledger, sc)
            cycles.append(ledger["entries"][-1])
            if ledger["entries"][-1]["status"] != "promoted":
                break
        if args.bad_demo:
            n += 1
            bad_steps = bad_mutation(active)
            log(f"\n--- cycle {n}: injected bad mutation")
            active, base_rep, _ = run_cycle(n, active, bad_steps, "v1.3-bad", tasks, base_rep, ledger, sc)
            cycles.append(ledger["entries"][-1])
    except clients.ApiError as e:
        log(f"\nBLOCKED: sponsor call failed: {e}. Ledger not updated for this cycle.")
        save_json(ledger_p, ledger)
        return 2

    save_json(skill_p, active)
    save_json(ledger_p, ledger)
    validate.check_ledger(ledger)
    promoted_entry = next((e for e in reversed(ledger["entries"])
                           if e["status"] == "promoted" and e["version"] == active["version"]), None)
    pinfo = skill_prompt.write_active(active, tasks, base_rep, promoted_entry)
    log(f"[9] Active prompt for {active['version']}: {pinfo['path']} ({pinfo['rules']} rules, sha256 {pinfo['sha256'][:12]})")
    target = args.sync_prompt or os.environ.get("PROOFLOOP_PROMPT_TARGET")
    prompt_sync = None
    if target and active["version"] == BASE_SKILL["version"]:
        log("[9] Prompt target left unchanged: no promoted skill yet, so the existing prompt is not downgraded")
    elif target:
        try:
            prompt_sync = skill_prompt.sync_block(target, pinfo["block"], create=args.create_target)
            log(f"[9] Prompt synced to {target}: {prompt_sync}")
        except (OSError, ValueError) as e:
            log(f"[9] Prompt sync FAILED, target not changed: {e}")
            prompt_sync = "failed"
    save_json(run_p, {
        "prompt": {k: pinfo[k] for k in ("path", "sha256", "version", "rules")} | {"target": target, "sync": prompt_sync},
        "generated": now(), "services": config.status(), "recall": recall_note,
        "initial": initial, "active": {"version": active["version"], "passed": base_rep["passed"],
                                       "total": base_rep["total"], "steps": active["steps"]},
        "tasks": [{"id": t["id"], "query": t["query"], "checks": t["required_checks"]} for t in tasks],
        "final_results": [{k: r[k] for k in ("task_id", "passed", "failed_checks")} for r in base_rep["results"]],
        "cycles": cycles,
    })
    log(f"\nDone. Active {active['version']}: {base_rep['passed']}/{base_rep['total']}. "
        f"Ledger: {ledger_p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
