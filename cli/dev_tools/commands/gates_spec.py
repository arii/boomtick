"""Issue-spec validation and scope-gate commands."""
import os
import sys
import re
import click
from dev_tools.utils import run_command
from dev_tools.commands.core import _gate_json_option
from dev_tools.commands.core import _handle_unexpected_error
from dev_tools.commands.core import cli
from dev_tools.commands.core import out
from dev_tools.commands.gates_audit import _prune_walk_dirs
from dev_tools.commands.gates_audit import _worktree_changed_files


def _read_spec_source(file):
    """Read spec text from a path, or stdin when file is '-'."""
    if file == "-":
        return sys.stdin.read()
    with open(file, encoding="utf-8") as handle:
        return handle.read()


def _spec_section_lines(body, *headings):
    """Raw lines of the first section whose heading matches."""
    wanted = {h.lower() for h in headings}
    capture = False
    lines = []
    for line in (body or "").splitlines():
        match = re.match(r"^#{1,3}\s+(.+?)\s*$", line.strip())
        if match:
            if capture:
                break
            capture = match.group(1).strip().lower() in wanted
            continue
        if capture:
            lines.append(line)
    return lines


def _spec_backtick_paths(body, *headings):
    """Backtick-quoted paths inside the given sections."""
    paths = []
    for line in _spec_section_lines(body, *headings):
        for path in re.findall(r"`([^`]+)`", line):
            path = path.strip()
            if path and path not in paths:
                paths.append(path)
    return paths


def _spec_checklist_items(body):
    """Checkbox acceptance criteria lines in document order."""
    items = []
    for line in (body or "").splitlines():
        match = re.match(r"^\s*[-*]\s+\[[\sxX]\]\s+(.+?)\s*$", line)
        if match:
            items.append(match.group(1))
    return items


def _spec_fenced_commands(body):
    """Bash commands from fenced blocks in the Verification section."""
    lines = _spec_section_lines(
        body, "verification", "verification commands", "validation")
    commands = []
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and stripped and not stripped.startswith("#"):
            commands.append(stripped)
    return commands


@cli.command(name="validate-issue")
@click.option("--file", "file", required=True,
              help="Path to the spec markdown file, or '-' for stdin")
@click.option("--repo-root", "repo_root", default=None,
              help="Checkout for scope existence checks (default: git root)")
@_gate_json_option
@click.pass_context
def validate_issue_spec(ctx, file, repo_root):
    """Validate a design spec file deterministically (exit 0 iff valid).

    Emits {"valid", "allowed_files", "forbidden_files",
    "verification_commands", "acceptance_criteria", "errors"}.
    """
    from dev_tools.services import local_sessions as ls
    from dev_tools.services import spec_issue as spec
    try:
        body = _read_spec_source(file)
        title = ""
        for line in body.splitlines():
            match = re.match(r"^#\s+(.+?)\s*$", line.strip())
            if match:
                title = match.group(1)
                break
        if not title:
            for line in body.splitlines():
                if line.strip():
                    title = line.strip()
                    break
        root = ls.repo_root_for(repo_root)
        missing = spec.missing_headers(body)
        scope = spec.scope_status(title + "\n" + body, root)
        forbidden_files = _spec_backtick_paths(
            body, "forbidden files", "forbidden")
        forbidden_lower = {p.lower() for p in forbidden_files}
        actual = set()
        actual_dirs = set()
        for dirpath, dirnames, filenames in os.walk(root):
            _prune_walk_dirs(dirnames)
            for dirname in dirnames:
                actual_dirs.add(os.path.relpath(
                    os.path.join(dirpath, dirname), root).lower())
            for filename in filenames:
                actual.add(os.path.relpath(
                    os.path.join(dirpath, filename), root).lower())
        allowed_files = [item["path"] for item in scope
                         if item["path"] not in forbidden_lower]
        acceptance_criteria = _spec_checklist_items(body)
        verification_commands = _spec_fenced_commands(body)
        if not verification_commands:
            verification_commands = spec.detect_gates(root)
        errors = []
        for header in missing:
            errors.append(f"missing required section: {header}")
        command_refs = " ".join(
            verification_commands).lower()
        for item in scope:
            if item["path"] in forbidden_lower:
                continue
            if item["kind"] == "dir":
                if item["path"].strip("/").lower() in actual_dirs:
                    continue
            elif item["path"].lower() in actual:
                continue
            if item["path"].lower() in command_refs:
                continue
            same_line_created = any(
                item["path"].lower() in line.lower()
                and "(create)" in line.lower()
                for line in body.splitlines())
            if not same_line_created:
                errors.append(
                    f"allowed path not in checkout: {item['path']} "
                    "(mark with (CREATE) if it is a new file)")
        if re.search(r"\bTODO\b|\bTBD\b", body):
            errors.append("spec contains TODO/TBD placeholders")
        if not verification_commands:
            errors.append("no verification commands found")
        if not acceptance_criteria:
            errors.append("no acceptance criteria checklist found")
        data = {"valid": not errors,
                "allowed_files": allowed_files,
                "forbidden_files": forbidden_files,
                "verification_commands": verification_commands,
                "acceptance_criteria": acceptance_criteria,
                "errors": errors}
        if not ctx.obj["JSON"]:
            if data["valid"]:
                click.echo("spec is valid")
            else:
                click.echo("spec is NOT valid:")
                for error in errors:
                    click.echo(f"   ❌ {error}")
        out(ctx, f"spec valid: {data['valid']}.", data=data)
        if errors:
            sys.exit(1)
    except Exception as e:
        _handle_unexpected_error(ctx, "validate-issue", e)


@cli.command(name="verify-scope")
@click.option("--spec-file", "spec_file", required=True,
              help="Path to the validated design spec markdown file")
@click.option("--worktree", "worktree", required=True,
              help="Path to the worktree to gate")
@click.option("--auto-revert", is_flag=True, default=False,
              help="Revert files outside the allowed scope")
@_gate_json_option
@click.pass_context
def verify_scope_gate(ctx, spec_file, worktree, auto_revert):
    """Gate worktree changes against a spec file (exit 0 iff in scope).

    Emits {"passed", "modified_files", "violations"}.
    """
    from dev_tools.services import scope_gate
    try:
        with open(spec_file, encoding="utf-8") as handle:
            spec_text = handle.read()
        changed = _worktree_changed_files(worktree)
        passed, allowed, disallowed = scope_gate.check_scope(
            changed, spec_text, root=worktree)
        violations = sorted(set(disallowed))
        forbidden = _spec_backtick_paths(
            spec_text, "forbidden files", "forbidden")
        forbidden_norm = set()
        for entry in forbidden:
            norm = entry.strip().lower().lstrip("./")
            forbidden_norm.add(norm)
        for path in changed:
            lowered = path.lower()
            if any(lowered == norm or lowered.endswith("/" + norm)
                   for norm in forbidden_norm):
                if path not in violations:
                    violations.append(path)
        violations = sorted(set(violations))
        passed = not violations
        reverted = []
        if auto_revert and violations:
            for path in violations:
                full = os.path.join(worktree, path)
                if os.path.isdir(full):
                    continue
                if os.path.isfile(full):
                    tracked = run_command(
                        ["git", "-C", worktree, "ls-files",
                         "--error-unmatch", "--", path],
                        check=False)
                    if tracked.returncode == 0:
                        res = run_command(
                            ["git", "-C", worktree, "checkout",
                             "--", path],
                            check=False)
                    else:
                        try:
                            os.remove(full)
                            res = None
                        except OSError:
                            continue
                        reverted.append(path)
                        continue
                    if res.returncode == 0:
                        reverted.append(path)
            _, _, still_out = scope_gate.check_scope(
                [p for p in changed if p not in reverted],
                spec_text, root=worktree)
            violations = sorted(set(still_out))
            passed = not violations
        data = {"passed": passed,
                "modified_files": changed,
                "violations": violations,
                "reverted": reverted}
        if not ctx.obj["JSON"]:
            if passed:
                click.echo("✅ scope check passed")
            else:
                click.echo("❌ scope violations:")
                for path in violations:
                    click.echo(f"   ❌ {path}")
        out(ctx, f"scope passed: {passed}.", data=data)
        if not passed:
            sys.exit(1)
    except Exception as e:
        _handle_unexpected_error(ctx, "verify-scope", e)
