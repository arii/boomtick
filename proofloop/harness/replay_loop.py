#!/usr/bin/env python3
"""ProofLoop auto-repeat loop.

Each cycle: real LLM answers every replay task under the active rule set (N samples) -> train-split
failures -> Cognee recall for those failures -> the LLM mutator proposes a revised rule set grounded
in the recalled sessions and user feedback -> the same tasks are replayed under the proposal -> the
gate promotes, holds or rejects -> a promoted set is stored in Senso and read back -> repeat.

It stops when it converges (PATIENCE consecutive proposals that do not promote, or every train task
passes every sample) or at the --max-cycles safety cap. Nothing is injected: a rollback is recorded
only when a real proposal loses.

    PROOFLOOP_LIVE_SERVICES=twt,senso,cognee PROOFLOOP_ALLOW_SESSION_UPLOAD=1 python3 replay_loop.py
    python3 replay_loop.py --status
"""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

import clients
import config
import executor
import gate
import mutator
import recall as recall_mod
import rules as rules_mod
import skill_prompt
import tasks as tasks_mod
import validate
from atomic import atomic_write_json
from services import Services


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg=""):
    print(msg, flush=True)


def paths():
    d = config.STATE_DIR
    return {"rules": d / "active_rules.json", "ledger": d / "proof_ledger.json", "run": d / "last_run.json",
            "feedback": d / "feedback.jsonl"}


def load_json(p, default):
    return json.loads(p.read_text()) if p.exists() else default


def reset_state():
    for name in ("active_rules.json", "proof_ledger.json", "last_run.json", "active_prompt.md", "cognee_ingest.json"):
        p = config.STATE_DIR / name
        if p.exists():
            p.unlink()


def read_feedback(path, known_ids):
    """rule id -> times marked wrong. Lines with unknown ids are ignored."""
    counts = Counter()
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("action") == "rule_wrong" and rec.get("rule_id") in known_ids:
                counts[rec["rule_id"]] += 1
    return dict(counts)


def failures_of(result, suite):
    """Train-split failures only: the mutator never sees holdout tasks."""
    by_id = {t["id"]: t for t in suite["tasks"]}
    out = []
    for tid, r in result.items():
        if r["split"] != "train" or r["score"] == 1.0:
            continue
        failed = Counter(c for s in r["samples"] for c in s["failed"])
        sample = next((s["answer"] for s in r["samples"] if s["failed"]), "")
        out.append({"task_id": tid, "source_session_id": by_id[tid]["source_session_id"], "task_kind": by_id[tid]["task_kind"], "query": by_id[tid]["query"],
                    "score": r["score"], "failed_checks": dict(failed), "answer_sample": sample[:600]})
    return out


def gather_evidence(rec, fails, suite):
    by_id = {t["id"]: t for t in suite["tasks"]}
    evidence, seen = [], set()
    for f in fails:
        query = f"{f['query']} " + " ".join(c.split(':', 1)[1] for c in f["failed_checks"])
        for ex in rec.search(query):
            if ex["session_id"] not in seen:
                seen.add(ex["session_id"])
                evidence.append(ex | {"why": "Cognee recall"})
    # Each failing train task's own source session is always evidence, whether or not recall returned it: it is
    # the session the task was made from, so it is the most natural citation. Holdout tasks never reach here.
    for f in fails:
        sid = by_id[f["task_id"]]["source_session_id"]
        if sid not in seen:
            seen.add(sid)
            evidence.append(recall_mod.excerpt(rec.sessions[sid]) | {"why": "source session of a failing task"})
    return evidence


def next_version(v):
    return f"v{int(v[1:]) + 1}"


def promote(services, rules, scores, gate_rec):
    text = json.dumps({"type": "PROOFLOOP_RULESET", "rules": rules, "sha256": rules_mod.sha256(rules),
                       "scores": scores, "gate": gate_rec, "promoted_at": now()}, ensure_ascii=False, indent=1)
    title = f"ProofLoop rule set {rules['version']} {rules_mod.sha256(rules)[:12]} {now()}"
    return clients.senso_promote(services.senso, title, text, rules["version"]) | {"title": title}


def entry(cycle, version, parent, status, gate_rec, scores, rec, services, rules, **extra):
    return {"cycle": cycle, "timestamp": now(), "version": version, "parent_version": parent, "status": status,
            "gate": gate_rec, "scores": scores, "recall": {"mode": rec.mode, "queries": rec.queries},
            "llm": {"backend": services.llm_backend or "injected"}, "rules_sha256": rules_mod.sha256(rules), **extra}


def run(services, suite, sessions, *, samples=3, patience=3, max_cycles=12, recall_enabled=True, log=log):
    p = paths()
    sessions_by_id = {s["session_id"]: s for s in sessions}
    task_kinds = rules_mod.task_ids()
    rec = recall_mod.Recall(services.cognee, sessions, enabled=recall_enabled)
    if rec.mode == "live" and config.get("PROOFLOOP_ALLOW_SESSION_UPLOAD") != "1":
        raise config.Blocked("Cognee upload needs PROOFLOOP_ALLOW_SESSION_UPLOAD=1 (sessions.jsonl is redacted; confirm before uploading)")
    log(f"[recall] {rec.ingest()}")

    stored = load_json(p["rules"], None)
    active = stored["rules"] if stored else rules_mod.empty()
    ledger = load_json(p["ledger"], {"schema_version": 3, "active_version": active["version"], "entries": []})
    if ledger.get("schema_version") != 3:
        raise config.Blocked("ledger is from an older version; use a new PROOFLOOP_STATE directory or --reset")
    rules_mod.validate(active, sessions_by_id)

    log(f"[baseline] {active['version']}: replaying {len(suite['tasks'])} tasks x {samples} samples")
    base = executor.run(services, active, suite["tasks"], samples, log)
    base_scores = executor.summary(base)
    log(f"[baseline] train {base_scores['train']}, holdout {base_scores['holdout']}")
    if not ledger["entries"]:
        ledger["entries"].append(entry(0, active["version"], None, "baseline", {}, base_scores, rec, services, active))
        atomic_write_json(p["ledger"], ledger)

    rejected, stale, proposals, stop = set(), 0, 0, ""
    cycle = max((e["cycle"] for e in ledger["entries"]), default=0)
    while True:
        fails = failures_of(base, suite)
        if not fails:
            stop = "converged: every train task passes every sample"
            break
        if stale >= patience:
            stop = f"converged: {patience} consecutive proposals did not beat the active rule set"
            break
        if proposals >= max_cycles:
            stop = f"stopped at the safety cap of {max_cycles} cycles (not converged)"
            break
        cycle += 1
        proposals += 1
        version = next_version(max((e["version"] for e in ledger["entries"]), key=lambda v: int(v[1:]), default=active["version"]))
        evidence = gather_evidence(rec, fails, suite)
        feedback = read_feedback(p["feedback"], {r["id"] for r in active["page_rules"]})
        log(f"\n--- cycle {cycle}: {len(fails)} failing train tasks, {len(evidence)} recalled sessions ({rec.mode}), feedback {feedback or 'none'}")
        try:
            cand = mutator.propose(services, active, fails, evidence, feedback, rejected, version, sessions_by_id, task_kinds)
        except mutator.InvalidProposal as e:
            log(f"    invalid proposal: {e}")
            ledger["entries"].append(entry(cycle, version, active["version"], "invalid_proposal", {"reason": str(e)[:300]},
                                           base_scores, rec, services, active, evidence_sessions=[x["session_id"] for x in evidence]))
            atomic_write_json(p["ledger"], ledger)
            stale += 1
            continue
        d = rules_mod.diff(active, cand)
        log("    proposal diff:\n      " + d.replace("\n", "\n      "))
        res = executor.run(services, cand, suite["tasks"], samples, log)
        scores = executor.summary(res)
        g = gate.decide(base, res, samples)
        log(f"    gate: {g['choice']} ({g['reason']})")
        status, senso = {"promote": "promoted", "hold": "held", "reject": "rejected"}[g["choice"]], {}
        if status == "promoted":
            try:
                senso = promote(services, cand, scores, g)
                log(f"    Senso: stored node {senso['node_id']}, readback verified")
            except clients.ApiError as e:
                status, senso = "promotion_failed", {"error": str(e)[:300]}
                log(f"    Senso promotion failed, active set unchanged: {e}")
        ledger["entries"].append(entry(cycle, version, active["version"], status, g, scores, rec, services, cand,
                                       diff=d, evidence_sessions=[x["session_id"] for x in evidence], senso=senso))
        if status == "promoted":
            active, base, base_scores, stale = cand, res, scores, 0
            ledger["active_version"] = cand["version"]
            atomic_write_json(p["rules"], {"rules": cand, "sha256": rules_mod.sha256(cand), "scores": scores,
                                           "senso": senso, "promoted_at": now()})
        else:
            rejected.add(rules_mod.content_sha(cand))
            stale += 1
        atomic_write_json(p["ledger"], ledger)

    validate.check_ledger(ledger)
    log(f"\n{stop}. Active {active['version']}: train {base_scores['train']}, holdout {base_scores['holdout']}")
    return {"active": active, "scores": base_scores, "stop": stop, "ledger": ledger,
            "senso": (load_json(p["rules"], {}) or {}).get("senso")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="clear rule set, ledger and run state in PROOFLOOP_STATE")
    ap.add_argument("--samples", type=int, default=3, help="LLM samples per task per evaluation")
    ap.add_argument("--patience", type=int, default=3, help="stop after this many proposals in a row fail to promote")
    ap.add_argument("--max-cycles", type=int, default=12, help="safety cap on proposals")
    ap.add_argument("--no-recall", action="store_true", help="run without Cognee (recorded as recall: disabled)")
    ap.add_argument("--generate-tasks", action="store_true", help="generate data/replay_tasks.json first if it is missing")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--sync-prompt", metavar="PATH", help="write the active prompt into PATH between PROOFLOOP markers "
                    "(also PROOFLOOP_PROMPT_TARGET). Only .md/.mdc/.txt files; never .env or .git")
    ap.add_argument("--create-target", action="store_true")
    args = ap.parse_args()

    if args.status:
        print(json.dumps(config.status(), indent=2))
        return 0
    try:
        services = Services.live(need=("llm", "senso") if args.no_recall else ("llm", "senso", "cognee"))
        if args.reset:
            reset_state()
        sessions = validate.load_sessions()
        suite = validate.load_suite()
        if suite is None:
            if not args.generate_tasks:
                raise config.Blocked("data/replay_tasks.json does not exist. Run tasks.py --generate (or pass --generate-tasks)")
            suite, _ = tasks_mod.generate(services, sessions, log)
            atomic_write_json(tasks_mod.SUITE_PATH, suite)
        if not suite["generated"]["reviewed"]:
            log("NOTE: replay_tasks.json has not been reviewed (generated.reviewed is false)")
        out = run(services, suite, sessions, samples=args.samples, patience=args.patience,
                  max_cycles=args.max_cycles, recall_enabled=not args.no_recall)
    except config.Blocked as e:
        log(f"BLOCKED: {e}")
        return 2
    except clients.ApiError as e:
        log(f"BLOCKED: service call failed: {e}. State from completed cycles is saved.")
        return 2

    pinfo = skill_prompt.write_active(out["active"], out["scores"], out["senso"])
    log(f"[prompt] {pinfo['path']} ({pinfo['rules']} rules, sha256 {pinfo['sha256'][:12]})")
    target = args.sync_prompt or os.environ.get("PROOFLOOP_PROMPT_TARGET")
    sync = None
    if target and out["active"]["version"] == "v0":
        log("[prompt] target left unchanged: nothing promoted yet")
    elif target:
        try:
            sync = skill_prompt.sync_block(target, pinfo["block"], create=args.create_target)
            log(f"[prompt] synced to {target}: {sync}")
        except (OSError, ValueError) as e:
            log(f"[prompt] sync FAILED, target not changed: {e}")
            sync = "failed"
    atomic_write_json(paths()["run"], {"generated": now(), "stop": out["stop"], "services": config.status(),
                                       "active": {"version": out["active"]["version"], "scores": out["scores"]},
                                       "prompt": {k: pinfo[k] for k in ("path", "sha256", "version", "rules")} | {"target": target, "sync": sync}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
