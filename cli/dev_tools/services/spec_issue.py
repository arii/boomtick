"""Turn an existing issue into an agent-implementable spec (deterministic).

``spec_issue()`` fetches nothing itself: it takes issue title + body and
a checkout path, then reports template conformance, extracts the scope
(file/dir mentions per the CI gate's regexes) with existence checks,
detects the repo's validation gates, and renders an improved body with
``## Agent scope`` + ``## Validation`` sections appended (idempotent).
No LLM: it structures and verifies, never invents scope.
"""

import json
import os
import re

from dev_tools.services import scope_gate

# Headers an agent needs to implement without follow-up questions.
REQUIRED_HEADERS = (
    "Problem Statement",
    "Goal",
    "Scope",
    "Definition of Done",
)

SCOPE_HEADING = "## Agent scope"
VALIDATION_HEADING = "## Validation"


def _headers(body):
    found = set()
    for line in (body or "").splitlines():
        match = re.match(r"^#{1,3}\s+(.+?)\s*$", line.strip())
        if match:
            found.add(match.group(1).strip().lower())
    return found


def missing_headers(body):
    """Required template headers absent from the body (original case).

    Substring match: scaffold headers like "SPECIFY SCOPE" and the
    appended "## Agent scope" both satisfy "Scope".
    """
    found = _headers(body)
    return [h for h in REQUIRED_HEADERS
            if not any(h.lower() in f for f in found)]


def scope_status(body, checkout):
    """Mentioned paths with existence: [{path, kind, status}]."""
    files, dirs = scope_gate.extract_mentions(
        (body or "") + "\n")
    items = []
    for path in sorted(files):
        full = os.path.join(checkout, path)
        items.append({
            "path": path,
            "kind": "file",
            "status": "in checkout" if os.path.isfile(full)
            else "NEW - confirm (not in checkout)",
        })
    for path in sorted(dirs):
        clean = path.strip("/")
        full = os.path.join(checkout, clean)
        items.append({
            "path": path,
            "kind": "dir",
            "status": "in checkout" if os.path.isdir(full)
            else "NEW - confirm (not in checkout)",
        })
    return items


def detect_gates(checkout):
    """Validation commands detected in the checkout (deterministic)."""
    gates = []
    pyproject = os.path.join(checkout, "pyproject.toml")
    has_pytest = (
        os.path.exists(os.path.join(checkout, "pytest.ini"))
        or os.path.exists(os.path.join(checkout, "setup.cfg"))
    )
    if os.path.isfile(pyproject):
        try:
            with open(pyproject, encoding="utf-8") as handle:
                content = handle.read()
            if "[tool.pytest" in content or "pytest" in content:
                has_pytest = True
        except OSError:
            pass
    if has_pytest:
        gates.append("python3 -m pytest <touched-test-paths>")
    pkg = os.path.join(checkout, "package.json")
    if os.path.isfile(pkg):
        try:
            with open(pkg, encoding="utf-8") as handle:
                scripts = json.load(handle).get("scripts", {})
        except (OSError, ValueError):
            scripts = {}
        if isinstance(scripts, dict):
            if "test" in scripts:
                gates.append("pnpm test (or pnpm --filter <pkg> test)")
            if "lint" in scripts:
                gates.append("pnpm run lint")
            if "type-check" in scripts:
                gates.append("pnpm run type-check")
    if os.path.isfile(os.path.join(checkout, "scripts", "verify-scope.py")):
        gates.append("python3 scripts/verify-scope.py --strict-scope "
                     "(changes limited to the scope files above)")
    else:
        gates.append("Scope: changes limited to the scope files above")
    return gates


def render_body(title, body, checkout):
    """Improved body + report dict (idempotent section append)."""
    body = body or ""
    missing = missing_headers(body)
    scope = scope_status(title + "\n" + body, checkout)
    gates = detect_gates(checkout)
    has_scope = SCOPE_HEADING.lower() in body.lower()
    has_validation = VALIDATION_HEADING.lower() in body.lower()
    out = body.rstrip()
    if not has_scope:
        lines = ["", "", SCOPE_HEADING,
                 "Allowed files/dirs (scope gate enforces):"]
        if scope:
            for item in scope:
                lines.append(
                    f"- `{item['path']}` ({item['status']})")
        else:
            lines.append("- (no file paths mentioned - add them before "
                         "dispatch)")
        out += "\n".join(lines)
    if not has_validation:
        lines = ["", "", VALIDATION_HEADING]
        for gate in gates:
            lines.append(f"- [ ] `{gate}`")
        out += "\n".join(lines)
    # Ready means: scope paths exist to enforce and the template is
    # complete. Sections are appended above when missing, so readiness
    # depends on content, not on whether we just added the headings.
    ready = bool(scope) and not missing
    return out + "\n", {
        "ready": ready,
        "missing_headers": missing,
        "scope": scope,
        "gates": gates,
        "sections_added": [
            s for s, had in (("agent scope", has_scope),
                             ("validation", has_validation)) if not had
        ],
    }
