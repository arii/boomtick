"""Turn the active (promoted) skill into a prompt agents can follow, and keep it current.

After a promotion the replay loop renders the active rule set into one marked block. The block is written to <state>/active_prompt.md and, when the operator
names a target file, into that file between PROOFLOOP markers. Nothing outside the markers is
touched. A rollback or a rejected candidate leaves the previous block in place, because the block
is rendered only from the active rule set.
"""
import hashlib
import os
import re
from pathlib import Path

import config
import rules as rules_mod
from atomic import atomic_write_text

BEGIN = "<!-- PROOFLOOP:BEGIN -->"
END = "<!-- PROOFLOOP:END -->"
ALLOWED_SUFFIXES = {".md", ".mdc", ".txt"}
_BLOCK_RE = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)


def render(rules, scores=None, senso=None):
    """Prompt block for the active rule set. `scores` is executor.summary(); `senso` the promotion record."""
    lines = [BEGIN, f"## ProofLoop rules for agents ({rules['version']})", ""]
    if scores:
        lines += [f"Promoted by the replay gate: train {scores.get('train')}, holdout {scores.get('holdout')} "
                  "(mean pass rate of real LLM answers on replayed past sessions). A measured result, not a guarantee.", ""]
    lines.append(rules_mod.render_prompt(rules))
    if senso and senso.get("node_id"):
        lines += ["", f"Stored in Senso as node {senso['node_id']}."]
    lines.append(END)
    return "\n".join(lines) + "\n"


def write_active(rules, scores=None, senso=None):
    """Write <state>/active_prompt.md. Returns {path, sha256, version, rules, block}."""
    block = render(rules, scores, senso)
    path = config.STATE_DIR / "active_prompt.md"
    atomic_write_text(path, block)
    return {"path": str(path), "sha256": hashlib.sha256(block.encode()).hexdigest(), "version": rules["version"],
            "rules": len(rules["instructions"]) + len(rules["page_rules"]), "block": block}


def _safe_target(target):
    p = Path(target).expanduser().resolve()
    if p.name.startswith(".env") or ".git" in p.parts or p.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError(f"refusing to write the prompt to {p.name}: only {sorted(ALLOWED_SUFFIXES)} files, never .env or .git")
    return p


def sync_block(target, block, create=False):
    """Insert or replace the PROOFLOOP block in `target`. Returns 'created', 'updated' or 'unchanged'."""
    p = _safe_target(target)
    if p.exists():
        old = p.read_text()
    elif create:
        old = None
        p.parent.mkdir(parents=True, exist_ok=True)
    else:
        raise FileNotFoundError(f"{p} does not exist (pass --create-target to create it)")
    if old is None:
        new, status = block, "created"
    elif BEGIN in old or END in old:
        if not _BLOCK_RE.search(old):
            raise ValueError(f"{p.name} has a PROOFLOOP marker without its pair; fix it by hand, nothing was written")
        new = _BLOCK_RE.sub(lambda _m: block, old, count=1)
        status = "unchanged" if new == old else "updated"
    else:
        new = old + ("" if old.endswith("\n\n") or not old else ("\n" if old.endswith("\n") else "\n\n")) + block
        status = "updated"
    if status != "unchanged":
        mode = p.stat().st_mode & 0o777 if p.exists() else None
        atomic_write_text(p, new)
        if mode is not None:
            os.chmod(p, mode)
    return status
