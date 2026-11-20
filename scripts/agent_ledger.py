#!/usr/bin/env python3
"""agent_ledger.py - shared-store CLI for the agent ledger.

One shared task store (intake form -> response Sheet -> hourly versioned
ledger snapshots in Drive) that any assistant can use from the command line:

  post     agent_ledger.py post --source NAME --note "task" --status Act [--link URL]
  new      agent_ledger.py new --source NAME --note "task" --status Act
           (mints a stable task-<id> key into the Link field - use this for
           tasks that have no URL, otherwise they get no stable identity)
  update   agent_ledger.py update --key KEY --source NAME --status STATUS [--note "..."]
           (appends a new intake row under the same key: this is how status
           changes and owner changes are recorded; latest row per key wins)
  claim    agent_ledger.py claim --key KEY --source NAME
           (= update with status Act; the reader folds owner = source of the
           latest row under that key, one owner at a time)
  read     agent_ledger.py read [--store-file PATH]
           (current state folded by key from the newest ledger snapshot)
  history  agent_ledger.py history --key KEY [--store-file PATH]
           (every recorded state of one task, oldest first)

Write path: the public intake form, no auth (any runtime can post).
Read path: the private ledger file in Drive. Live read needs the assistant's
OWN Google credential (per-assistant Drive access, no shared tokens):
  export AGENT_LEDGER_TOKEN=$(gcloud auth application-default print-access-token)
  export AGENT_LEDGER_FILE_ID=<drive file id of agent-ledger.jsonl>
For offline/testing, --store-file reads a local copy of the ledger instead.
Fails closed: without a token or store file, read/history exit 1.

Config: AGENT_LEDGER_FORM_URL (or --form-url) is required for post/new/
update/claim. No default is baked in.
"""

import argparse, json, sys, time, uuid, urllib.parse, urllib.request

ENTRY_SOURCE = "entry.421540333"  # Agent / Source
ENTRY_NOTE = "entry.526880121"  # Item / Note
ENTRY_STATUS = "entry.910915240"  # Status (Act / Later / Needs Okay / Done)
ENTRY_LINK = "entry.1391612799"  # Link (doubles as the stable task key)

STATUSES = ["Act", "Later", "Needs Okay", "Done"]


def post_row(form_url, source, note, status, link, dry_run):
    data = {
        ENTRY_SOURCE: source,
        ENTRY_NOTE: note,
        ENTRY_STATUS: status,
        ENTRY_LINK: link or "",
    }
    if dry_run:
        return {"dry_run": True, "fields": data}
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(form_url, data=body)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return {
            "submitted": resp.status == 200,
            "http_status": resp.status,
            "source": source,
            "note": note,
            "status": status,
            "link": link or None,
        }


def load_snapshots(args):
    if args.store_file:
        with open(args.store_file) as f:
            lines = [l for l in f if l.strip()]
    else:
        import os

        token = os.environ.get("AGENT_LEDGER_TOKEN")
        file_id = os.environ.get("AGENT_LEDGER_FILE_ID")
        if not token or not file_id:
            print(
                json.dumps(
                    {
                        "error": "live read needs AGENT_LEDGER_TOKEN and "
                        "AGENT_LEDGER_FILE_ID (assistant's own Google "
                        "credential), or --store-file for a local copy"
                    }
                )
            )
            sys.exit(1)
        req = urllib.request.Request(
            "https://www.googleapis.com/drive/v3/files/%s?alt=media" % file_id,
            headers={"Authorization": "Bearer " + token},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            lines = [l for l in resp.read().decode().splitlines() if l.strip()]
    return [json.loads(l) for l in lines if json.loads(l).get("type") == "snapshot"]


def cmd_read(args):
    snaps = load_snapshots(args)
    if not snaps:
        print(json.dumps({"error": "no snapshots in store"}))
        sys.exit(1)
    latest = snaps[-1]
    out = []
    for r in latest["rows"]:
        out.append(
            {
                "key": r["key"],
                "status": r["status"],
                "owner": r.get("owner") or r.get("source"),
                "updated": r.get("updated"),
                "note": r["note"],
            }
        )
    # the store lags live state by the export cadence; warn rather than let
    # stale state read as fresh
    stale = None
    try:
        import datetime

        cap = datetime.datetime.fromisoformat(
            latest["captured_at"].replace("Z", "+00:00")
        )
        age_min = (
            datetime.datetime.now(datetime.timezone.utc) - cap
        ).total_seconds() / 60
        if age_min > 75:
            stale = (
                "snapshot is %d minutes old (export cadence ~60m); state may have changed since"
                % age_min
            )
    except Exception:
        stale = "snapshot timestamp unparsable; freshness unknown"
    result = {"seq": latest["seq"], "captured_at": latest["captured_at"], "items": out}
    if stale:
        result["warning"] = stale
    print(json.dumps(result, indent=2))


def cmd_history(args):
    snaps = load_snapshots(args)
    states = []
    for s in snaps:
        for r in s["rows"]:
            if r["key"] == args.key:
                states.append(
                    {
                        "seq": s["seq"],
                        "captured_at": s["captured_at"],
                        "status": r["status"],
                        "source": r.get("source"),
                        "note": r["note"],
                    }
                )
    if not states:
        print(json.dumps({"error": "key not found", "key": args.key}))
        sys.exit(1)
    print(json.dumps({"key": args.key, "states": states}, indent=2))


def main():
    ap = argparse.ArgumentParser(prog="agent_ledger.py")
    ap.add_argument(
        "--form-url", default=__import__("os").environ.get("AGENT_LEDGER_FORM_URL")
    )
    ap.add_argument("--dry-run", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_write(p, need_note=True, need_key=False):
        p.add_argument(
            "--source",
            required=True,
            help="your assistant name (becomes owner on claim)",
        )
        p.add_argument("--status", choices=STATUSES, default=None)
        if need_note:
            p.add_argument("--note", required=True)
        if need_key:
            p.add_argument(
                "--key", required=True, help="URL or task-<id> from 'new'/'read'"
            )
        else:
            p.add_argument("--link", default="")

    add_write(sub.add_parser("post"))
    add_write(sub.add_parser("new"))
    p = sub.add_parser("update")
    add_write(p, need_key=True)
    p = sub.add_parser("claim")
    add_write(p, need_note=False, need_key=True)
    p = sub.add_parser("read")
    p.add_argument("--store-file")
    p = sub.add_parser("history")
    p.add_argument("--key", required=True)
    p.add_argument("--store-file")

    args = ap.parse_args()

    if args.cmd in ("read", "history"):
        (cmd_read if args.cmd == "read" else cmd_history)(args)
        return 0

    if not args.form_url:
        print(
            json.dumps(
                {
                    "error": "form URL required: set AGENT_LEDGER_FORM_URL or pass --form-url"
                }
            )
        )
        return 1
    # Submissions only land at /formResponse; accept the shareable /viewform
    # link too and convert it (posting to /viewform answers 405).
    if "/viewform" in args.form_url:
        args.form_url = args.form_url.split("/viewform", 1)[0] + "/formResponse"

    if args.cmd == "new":
        key = "task-" + uuid.uuid4().hex[:12]
        res = post_row(
            args.form_url,
            args.source,
            args.note,
            args.status or "Act",
            key,
            args.dry_run,
        )
        res["key"] = key
    elif args.cmd == "claim":
        res = post_row(
            args.form_url,
            args.source,
            "claimed by " + args.source,
            "Act",
            args.key,
            args.dry_run,
        )
        res["key"] = args.key
    elif args.cmd == "update":
        res = post_row(
            args.form_url,
            args.source,
            args.note,
            args.status or "Act",
            args.key,
            args.dry_run,
        )
        res["key"] = args.key
    else:
        res = post_row(
            args.form_url,
            args.source,
            args.note,
            args.status or "Act",
            args.link,
            args.dry_run,
        )
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
