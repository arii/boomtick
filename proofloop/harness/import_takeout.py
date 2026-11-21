"""Convert a Gemini Takeout zip into schema-valid, redacted sessions JSONL.

Run locally; write output to a private path (default data/private/, git-ignored).
Usage: python -m harness.import_takeout ZIP [--out PATH] [--limit N]
Keeps only conversations that look code-related, redacts PII, truncates text.
"""
import argparse, json, re, zipfile
from pathlib import Path

CODE_HINT = re.compile(r"\b(error|traceback|exception|python|npm|git|docker|api|function|bug|compile|stack ?trace|import)\b", re.I)
FAIL_HINT = re.compile(r"\b(error|failed|traceback|exception|doesn'?t work|not working|404|403|500)\b", re.I)
REDACT = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"\+?\d[\d\s().-]{8,}\d"), "[PHONE]"),
    (re.compile(r"\b(?:sk|key|tok|ghp|xox)[-_][A-Za-z0-9_-]{12,}\b"), "[KEY]"),
    (re.compile(r"/(?:home|Users)/[^/\s]+"), "/home/[USER]"),
]

def redact(s: str) -> str:
    for rx, rep in REDACT:
        s = rx.sub(rep, s)
    return s

def clip(s: str, n: int) -> str:
    s = " ".join(redact(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"

def convert(conv: dict, name: str):
    turns = conv.get("conversation_turns") or []
    pairs = [((t.get("user_turn") or {}).get("prompt", ""), (t.get("system_turn") or {}).get("text", "")) for t in turns]
    pairs = [p for p in pairs if p[0]]
    blob = " ".join(p[0] + " " + p[1] for p in pairs)
    if len(CODE_HINT.findall(blob)) < 3:
        return None
    fail = next((p for p in pairs if FAIL_HINT.search(p[0])), pairs[0] if pairs else None)
    if not fail:
        return None
    sid = "sess_takeout_" + re.sub(r"\W+", "_", Path(name).stem)[:40]
    return {
        "session_id": sid,
        "timestamp": conv.get("create_time") or "2026-01-01T00:00:00Z",
        "role": "user",
        "query_or_task": clip(pairs[0][0], 200),
        "outcome_or_error": clip(fail[0] + " -> " + fail[1], 400),
        "constraint": "TODO: review by hand and write the one-line rule this session teaches.",
        "active_tab": {"title": "Gemini chat", "url": "https://gemini.google.com/", "snippet": ""},
        "related_tabs": [],
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zip")
    ap.add_argument("--out", default="data/private/sessions.takeout.jsonl")
    ap.add_argument("--limit", type=int, default=50)
    a = ap.parse_args()
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(a.zip) as z, out.open("w") as f:
        for name in sorted(z.namelist()):
            if not name.endswith(".json") or n >= a.limit:
                continue
            try:
                row = convert(json.loads(z.read(name)), name)
            except (ValueError, AttributeError):
                continue
            if row:
                f.write(json.dumps(row, ensure_ascii=False) + "\n"); n += 1
    print(f"wrote {n} rows to {out}; review constraints by hand before sharing")

if __name__ == "__main__":
    main()
