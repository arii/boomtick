#!/usr/bin/env python3
"""Check that Code.gs normalize() matches Python normalize() on every assigned code point.

Reference: CPython 3.11 (Unicode 14.0.0). Run this when the Python or Apps Script (V8) runtime
is upgraded. It also checks that the hash vectors use only code points assigned in Unicode 14.

    python3.11 apps-script/agent-ledger-hook/check_unicode_parity.py

Needs node (any recent version; Code.gs runs in a vm context). Exits 1 on any difference or on
an unassigned code point in the vectors. The Python normalize() below mirrors
scripts/ledger_intake.py in arii/remote-server: NFKC, strip, casefold, collapse whitespace.
"""

import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
VECTORS = HERE.parents[1] / "tests/fixtures/agent-ledger/intake-hash-vectors.json"
JS = """
const fs = require('fs'), vm = require('vm');
const ctx = {Utilities: {}};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8') + '\\nthis.normalize = normalize;', ctx);
const texts = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(texts.map(ctx.normalize)));
"""


def normalize(value):
    text = unicodedata.normalize("NFKC", value or "").strip().casefold()
    return re.sub(r"\s+", " ", text)


def js_normalize(texts):
    done = subprocess.run(
        ["node", "-e", JS, str(HERE / "Code.gs")],
        input=json.dumps(texts),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(done.stdout)


def main():
    print(f"Python {sys.version.split()[0]}, Unicode {unicodedata.unidata_version}")
    if unicodedata.unidata_version != "14.0.0":
        print(
            "Reference is Python 3.11 / Unicode 14.0.0; regenerate the vectors under 3.11."
        )
        return 1
    bad = 0
    vectors = json.loads(VECTORS.read_text(encoding="utf8"))["vectors"]
    for vector in vectors:
        for field in ("title", "repo"):
            for char in vector[field]:
                if unicodedata.category(char) == "Cn":
                    print(f"vector {vector[field]!r} has unassigned U+{ord(char):04X}")
                    bad += 1
    chars = [
        chr(cp)
        for cp in range(0x110000)
        if not 0xD800 <= cp <= 0xDFFF and unicodedata.category(chr(cp)) != "Cn"
    ]
    results = []
    for start in range(0, len(chars), 20000):
        results += js_normalize(chars[start : start + 20000])
    differ = [(c, normalize(c), r) for c, r in zip(chars, results) if normalize(c) != r]
    for char, want, got in differ[:20]:
        print(f"U+{ord(char):04X} python={want!r} js={got!r}")
    print(
        f"{len(chars)} assigned code points, {len(differ)} differences, {bad} unassigned in vectors"
    )
    return 1 if differ or bad else 0


if __name__ == "__main__":
    sys.exit(main())
