"""Code-audit and impact-analysis gate commands."""
import json
import os
import sys
import re
from pathlib import Path
import click
from dev_tools.utils import CLIError, run_command
from dev_tools.commands.core import _gate_json_option
from dev_tools.commands.core import _handle_unexpected_error
from dev_tools.commands.core import cli
from dev_tools.commands.core import out


def _worktree_changed_files(worktree):
    """Paths changed vs origin/main inside worktree (relative, sorted)."""
    res = run_command(["git", "diff", "--name-only", "origin/main", "--", "."],
                      check=False, cwd=worktree)
    if res.returncode != 0:
        raise CLIError(
            f"git diff origin/main failed in {worktree}: "
            f"{res.stderr or res.stdout}")
    return sorted(p for p in (res.stdout or "").splitlines() if p.strip())


def _td_package_root():
    """Root of the installed td package (holds scripts/ and .agents/)."""
    return os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", ".."))


def _resolve_audit_script(worktree, *candidates, need_config=None,
                          worktree_only=False):
    """First existing audit script: worktree checkout, then td package.

    need_config names a config file (relative to the script base) that
    must also exist, so repo-specific audits never run under another
    repo's config. worktree_only disables the td package fallback for
    audits that are only meaningful with the worktree's own config.
    """
    bases = (worktree,) if worktree_only else (worktree, _td_package_root())
    for base in bases:
        if need_config and not os.path.isfile(
                os.path.join(base, need_config)):
            continue
        for candidate in candidates:
            full = os.path.join(base, candidate)
            if os.path.isfile(full):
                return full
    return None


@cli.command(name="audit-code")
@click.option("--worktree", "worktree", required=True,
              help="Path to the worktree to audit")
@_gate_json_option
@click.pass_context
def audit_code_gate(ctx, worktree):
    """Audit worktree changes for slop and AST violations (exit 0 iff clean).

    Emits {"passed", "slop_findings", "suppressions_added",
    "ast_violations"}.
    """
    from dev_tools.services.ast_audit import ASTAuditor
    try:
        changed = _worktree_changed_files(worktree)
        code_files = [p for p in changed
                      if p.endswith((".py", ".ts", ".tsx", ".js",
                                     ".jsx", ".mjs", ".mts"))]
        auditor = ASTAuditor()
        ast_violations = []
        for rel in code_files:
            full = os.path.join(worktree, rel)
            if not os.path.isfile(full):
                continue
            try:
                with open(full, encoding="utf-8", errors="ignore") as handle:
                    code = handle.read()
                for finding in auditor.audit_file(rel, code) or []:
                    ast_violations.append({
                        "file": rel,
                        "rule": finding.get("rule"),
                        "message": finding.get("message"),
                        "line": finding.get("line"),
                        "severity": finding.get("severity"),
                    })
            except Exception:
                continue
        slop_findings = []
        slop_script = _resolve_audit_script(
            worktree, os.path.join(".agents", "scripts", "audit-ai-slop.py"),
            need_config=os.path.join(".agents", "audit.config.yaml"),
            worktree_only=True)
        if slop_script:
            res = run_command(["python3", slop_script], check=False,
                              cwd=worktree, log_on_error=False)
            output = res.stdout or ""
            match = re.search(r"Total [Vv]iolations[^0-9]{0,10}(\d+)",
                              output)
            count = int(match.group(1)) if match else -1
            if res.returncode != 0 or count != 0:
                slop_findings.append({
                    "script": os.path.basename(slop_script),
                    "exit_code": res.returncode,
                    "summary": output.strip()[-2000:],
                })
        antipattern_script = _resolve_audit_script(
            worktree, os.path.join("scripts", "detect-antipatterns.mjs"))
        if antipattern_script and code_files:
            res = run_command(["node", antipattern_script, "--json"]
                              + code_files,
                              check=False, cwd=worktree,
                              log_on_error=False)
            try:
                payload = json.loads((res.stdout or "")[
                    (res.stdout or "").find("{"):])
                for path, items in (
                        payload.get("violations") or {}).items():
                    for item in items or []:
                        ast_violations.append({
                            "file": os.path.relpath(path, worktree)
                            if os.path.isabs(path) else path,
                            "rule": (item or {}).get("pattern",
                                                     "antipattern"),
                            "message": (item or {}).get("message", ""),
                            "line": (item or {}).get("line"),
                            "severity": (item or {}).get("severity"),
                        })
            except (ValueError, AttributeError):
                if res.returncode != 0:
                    slop_findings.append({
                        "script": "detect-antipatterns.mjs",
                        "exit_code": res.returncode,
                        "summary": (res.stdout or res.stderr or "")[-2000:],
                    })
        suppressions_added = []
        suppression_script = _resolve_audit_script(
            worktree,
            os.path.join("scripts", "check-suppression-inventory.mjs"))
        if suppression_script:
            res = run_command(["node", suppression_script], check=False,
                              cwd=worktree, log_on_error=False)
            output = (res.stdout or "") + (res.stderr or "")
            for line in output.splitlines():
                if "added" in line.lower() and "suppression" in line.lower():
                    suppressions_added.append(line.strip())
        passed = (not ast_violations) and (not slop_findings)
        data = {"passed": passed,
                "slop_findings": slop_findings,
                "suppressions_added": suppressions_added,
                "ast_violations": ast_violations}
        if not ctx.obj["JSON"]:
            if passed:
                click.echo("✅ audit passed")
            else:
                click.echo(
                    f"❌ audit failed: "
                    f"{len(ast_violations)} AST/antipattern violation(s), "
                    f"{len(slop_findings)} slop finding(s)")
        out(ctx, f"audit passed: {passed}.", data=data)
        if not passed:
            sys.exit(1)
    except Exception as e:
        _handle_unexpected_error(ctx, "audit-code", e)


TEST_PATH_HINTS = ("/test_", "/tests/", "test_", "_test.",
                  ".test.", ".spec.")


def _is_test_path(path):
    lowered = path.lower()
    return (any(hint in lowered for hint in TEST_PATH_HINTS)
            or os.path.basename(lowered).startswith("test"))


# Directories never worth walking for impact/scope analysis: VCS,
# dependency installs, build output, caches, and test artifacts. Pruned
# in place during os.walk (see _prune_walk_dirs) so large checkouts
# (69k+ files under .venv/, dist/, test-results/) stay fast.
SKIP_WALK_DIRS = frozenset({
    ".git", "node_modules", ".venv", "venv", "dist", "build",
    "__pycache__", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".td_rag", ".worktrees", "test-results",
    "test_results", ".nyc_output", "coverage",
})


def _prune_walk_dirs(dirnames):
    """Drop heavy/irrelevant dirs from an os.walk traversal in place."""
    dirnames[:] = [d for d in dirnames
                   if d not in SKIP_WALK_DIRS
                   and not d.startswith(".tmp")
                   and not d.endswith(".egg-info")]
    return dirnames


def _impact_dependents(worktree, changed):
    """Files referencing a changed module (import/from/require).

    Returns {changed_path: [dependent paths]}. Best effort, read-only.
    """
    dependents = {path: [] for path in changed}
    stems = {}
    for path in changed:
        base = os.path.basename(path)
        stem, _ = os.path.splitext(base)
        stems.setdefault(stem, []).append(path)
    if not stems:
        return dependents
    for dirpath, dirnames, filenames in os.walk(worktree):
        _prune_walk_dirs(dirnames)
        for name in filenames:
            if not name.endswith((".py", ".ts", ".tsx", ".js",
                                   ".jsx", ".mjs")):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, worktree)
            if rel in dependents:
                continue
            try:
                with open(full, encoding="utf-8",
                          errors="ignore") as handle:
                    content = handle.read()
            except OSError:
                continue
            for stem, owners in stems.items():
                if not stem or len(stem) < 3:
                    continue
                escaped = re.escape(stem)
                import_ref = (
                    r"(?:from|import|require)[^\n]{0,120}?" + escaped)
                path_ref = (r"(?:^|[^a-zA-Z0-9_])" + escaped +
                            r"(?:\.[a-zA-Z_]|/)")
                if (re.search(import_ref, content)
                        or re.search(path_ref, content)):
                    for owner in owners:
                        dependents[owner].append(rel)
    for owner in dependents:
        dependents[owner] = sorted(set(dependents[owner]))
    return dependents


@cli.command(name="audit-impact")
@click.option("--worktree", "worktree", required=True,
              help="Path to the worktree to analyze")
@click.option("--top-k", "top_k", default=25, type=int,
              help="Maximum impacted files to list")
@click.option("--preview-url", "preview_url", default=None,
              help="Base URL of a live preview for the visual/DOM audit "
                   "of UI changes. Falls back to PREVIEW_URL.")
@_gate_json_option
@click.pass_context
def audit_impact_gate(ctx, worktree, top_k, preview_url):
    """Blast-radius analysis for worktree changes (exit 0 iff clean).

    Emits {"impacted_files", "dependent_tests", "violations",
    "ui_changed", "visual_diff"} where violations are AST findings
    on changed files. When changed files touch UI templates/styles
    and a preview URL is available, a remote-CDP snapshot is captured
    via browserless (never a local Chrome) and attached as
    "visual_diff"; an unreachable browser fails the gate. Nonzero
    exit when any violation exists.
    """
    from dev_tools.services.ast_audit import ASTAuditor
    try:
        changed = [p for p in _worktree_changed_files(worktree)
                   if not p.startswith((".td_rag/", ".worktrees/"))]
        auditor = ASTAuditor()
        violations = []
        for rel in changed:
            if not rel.endswith((".py", ".ts", ".tsx", ".js",
                                  ".jsx", ".mjs")):
                continue
            full = os.path.join(worktree, rel)
            if not os.path.isfile(full):
                continue
            try:
                with open(full, encoding="utf-8",
                          errors="ignore") as handle:
                    code = handle.read()
                for finding in auditor.audit_file(rel, code) or []:
                    violations.append({
                        "file": rel,
                        "rule": finding.get("rule"),
                        "message": finding.get("message"),
                        "line": finding.get("line"),
                        "severity": finding.get("severity"),
                    })
            except Exception:
                continue
        dependents = _impact_dependents(worktree, changed)
        impacted = sorted(set(changed)
                          | {d for deps in dependents.values()
                             for d in deps})[:top_k]
        dependent_tests = sorted(
            {d for deps in dependents.values() for d in deps
             if _is_test_path(d)}
            | {p for p in changed if _is_test_path(p)})[:top_k]
        ui_extensions = {".tsx", ".jsx", ".vue", ".html",
                         ".css", ".scss"}
        ui_changed = any(Path(f).suffix in ui_extensions
                         for f in changed)
        preview = preview_url or os.environ.get("PREVIEW_URL")
        visual_diff = None
        visual_error = None
        if ui_changed and preview:
            from dev_tools.services.browser_cdp import (
                capture_dom_and_visual_snapshot)
            snap = capture_dom_and_visual_snapshot(
                target_url=preview,
                output_dir=Path(worktree) / ".td_rag" / "snapshots",
            )
            visual_diff = snap.to_dict()
            if not snap.reachable:
                visual_error = snap.error or "BROWSER_UNREACHABLE"
        passed = not violations and visual_error is None
        data = {"passed": passed,
                "impacted_files": impacted,
                "dependent_tests": dependent_tests,
                "violations": violations,
                "ui_changed": ui_changed,
                "visual_diff": visual_diff}
        if visual_error:
            data["error"] = visual_error
        if not ctx.obj["JSON"]:
            if passed:
                click.echo(
                    f"✅ impact clean: {len(impacted)} file(s), "
                    f"{len(dependent_tests)} test(s)")
            else:
                click.echo(
                    f"❌ impact: {len(violations)} violation(s) in "
                    f"{len(impacted)} file(s)")
        out(ctx, f"impact clean: {passed}.", data=data)
        if not passed:
            sys.exit(1)
    except Exception as e:
        _handle_unexpected_error(ctx, "audit-impact", e)
