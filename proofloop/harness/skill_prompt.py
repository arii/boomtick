"""Turn the active (promoted) skill into a prompt agents can follow, and keep it current.

After a promotion the replay loop renders the active skill's steps and the constraints it passed
into one marked block. The block is written to <state>/active_prompt.md and, when the operator
names a target file, into that file between PROOFLOOP markers. Nothing outside the markers is
touched. A rollback or a rejected candidate leaves the previous block in place, because the block
is rendered only from the active skill.
"""
import hashlib
import os
import re
from pathlib import Path

import agent
import config

BEGIN = "<!-- PROOFLOOP:BEGIN -->"
END = "<!-- PROOFLOOP:END -->"
ALLOWED_SUFFIXES = {".md", ".mdc", ".txt"}
_BLOCK_RE = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)


def render(skill, tasks, report, entry=None):
    """Prompt block for `skill`. `report` is agent.replay(skill, tasks); `entry` the promoted ledger entry."""
    rules = [agent.PROMPT_RULES[s] for s in skill["steps"] if s in agent.PROMPT_RULES]
    passed = {r["task_id"] for r in report["results"] if r["passed"]}
    constraints = []
    for t in tasks:
        c = t["expected_constraint"]
        if t["id"] in passed and c not in constraints:
            constraints.append(c)
    lines = [
        BEGIN,
        f"## ProofLoop rules for agents (skill {skill['version']})",
        "",
        f"A local replay gate promoted this skill after it passed {report['passed']}/{report['total']} "
        "replayed tasks from past sessions. That is a measured replay result, not a guarantee.",
        "",
        "Follow these rules when acting for the user:",
    ]
    lines += [f"{i}. {r}" for i, r in enumerate(rules, 1)]
    if constraints:
        lines += ["", "Constraints learned from past sessions (each one passed replay under this skill):"]
        lines += [f"- {c}" for c in constraints]
    if entry and entry.get("senso_kb_node_id"):
        mode = (entry.get("retrieval") or {}).get("mode", "unknown")
        lines += ["", f"Stored in Senso as node {entry['senso_kb_node_id']} (retrieval mode: {mode})."]
    lines.append(END)
    return "\n".join(lines) + "\n"


def write_active(skill, tasks, report, entry=None):
    """Write <state>/active_prompt.md. Returns {path, sha256, version, rules, block}."""
    block = render(skill, tasks, report, entry)
    path = config.STATE_DIR / "active_prompt.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(block)
    return {"path": str(path), "sha256": hashlib.sha256(block.encode()).hexdigest(),
            "version": skill["version"], "rules": len([s for s in skill["steps"] if s in agent.PROMPT_RULES]),
            "block": block}


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
        tmp = p.with_name(p.name + ".proofloop.tmp")
        tmp.write_text(new)
        if p.exists():
            os.chmod(tmp, p.stat().st_mode & 0o777)
        os.replace(tmp, p)
    return status
