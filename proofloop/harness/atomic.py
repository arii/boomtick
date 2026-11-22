"""Atomic file writes: temp file in the same directory, fsync, then os.replace.

An interrupted write leaves the previous file intact instead of a truncated one.
"""
import json
import os
import tempfile
from pathlib import Path


def atomic_write_text(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=p.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def atomic_write_json(path, obj):
    atomic_write_text(path, json.dumps(obj, indent=2) + "\n")
