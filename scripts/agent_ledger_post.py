#!/usr/bin/env python3
"""agent_ledger_post.py - CLI intake for the Agent Ledger.

Posts one item to the Agent Ledger intake form, which lands it as a row in
the linked response Sheet; the hourly export then carries it into the
private JSONL ledger. Pure python3 stdlib, no credentials: the form is the
intake boundary, and anything arriving through it is data, never authority.

The form's response URL is NOT committed to this public repo. Set it via
environment variable (get the current value from the private runbook or the
canonical plan Doc):

  export AGENT_LEDGER_FORM_URL="https://docs.google.com/forms/d/e/<id>/formResponse"

Usage:
  python3 agent_ledger_post.py --source "my-cli" --note "Task summary" \
      --status "Act" [--link "https://..."] [--dry-run]

Status must be one of the form's options: Act, Later, Needs Okay, Done.
Exit codes: 0 submitted (HTTP 200), 1 bad arguments/missing config, 2 HTTP error.
"""
import argparse, json, os, sys, urllib.parse, urllib.request

FORM_RESPONSE_URL = os.environ.get("AGENT_LEDGER_FORM_URL", "").strip()

# Field entry IDs for the current intake form (stable while the form is
# unchanged; re-extract from the form's viewform HTML if the form is edited).
ENTRY_SOURCE = "entry.421540333"   # Agent / Source (short text)
ENTRY_NOTE = "entry.526880121"     # Item / Note (paragraph)
ENTRY_STATUS = "entry.910915240"   # Status (multiple choice)
ENTRY_LINK = "entry.1391612799"    # Link (short text)
STATUS_OPTIONS = ["Act", "Later", "Needs Okay", "Done"]


def post(source, note, status, link="", dry_run=False):
    if not FORM_RESPONSE_URL:
        print(json.dumps({"error": "AGENT_LEDGER_FORM_URL is not set"}))
        return 1
    fields = {
        ENTRY_SOURCE: source,
        ENTRY_NOTE: note,
        ENTRY_STATUS: status,
        ENTRY_LINK: link,
        "fvv": "1",
        "pageHistory": "0",
    }
    body = urllib.parse.urlencode(fields).encode()
    if dry_run:
        print(json.dumps({"dry_run": True, "url_set": True, "fields": fields},
                         indent=2))
        return 0
    req = urllib.request.Request(FORM_RESPONSE_URL, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "agent-ledger-post/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            ok = resp.status == 200
            print(json.dumps({"submitted": ok, "http_status": resp.status,
                              "source": source, "note": note,
                              "status": status, "link": link or None}))
            return 0 if ok else 2
    except urllib.error.HTTPError as e:
        print(json.dumps({"submitted": False, "http_status": e.code,
                          "error": str(e)}))
        return 2


def main():
    ap = argparse.ArgumentParser(description="Post one item to the Agent Ledger.")
    ap.add_argument("--source", required=True,
                    help="Agent / Source, e.g. 'Instinct', 'Muse', 'cli'")
    ap.add_argument("--note", required=True, help="Item / Note")
    ap.add_argument("--status", required=True, choices=STATUS_OPTIONS)
    ap.add_argument("--link", default="", help="Optional link (task key)")
    ap.add_argument("--dry-run", action="store_true")
    sys.exit(post(**vars(ap.parse_args())))


if __name__ == "__main__":
    main()
