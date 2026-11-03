"""Shipped port of scripts/verify-scope.py's matching core for td.

The CI gate script is not importable from installed td (hyphenated
filename outside the package), so the pure matching logic lives here
too. Behavioral parity is enforced by
cli/tests/test_scope_gate_conformance.py, which runs both
implementations over shared fixtures and asserts identical verdicts.
If you change matching rules, change BOTH files and keep the
conformance test green.

One principled extension: ``root`` anchors the import-heuristic file
reads (the script reads relative to cwd). ``root=None`` behaves
exactly like the script.
"""

import os
import re

EXEMPT_FILES = {
    "dockerfile", "package.json", "package-lock.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", "project_config.json",
    "tsconfig.json", "workspace.json", ".gitignore", ".dockerignore", ".pylintrc",
    "eslint.config.mjs", "oxlint.json", "tsconfig.app.json", ".release-please-manifest.json",
    "release-please-config.json", "changelog.md", "readme.md", "agents.md", "ci.yml", "release.yml",
    "verify-scope.py", "test_verify_scope.py", "reviewpromptconstants.ts",
    "prompt_constants.json", "pyproject.toml", "action.yml", ".dependency-cruiser.config.mjs",
    ".fallowrc.json", ".jscpd.json", ".node-version", ".npmrc", "tsup.config.ts",
    "workspace-schema.json", ".env.example"
}
EXEMPT_FILES_LOWER = {f.lower() for f in EXEMPT_FILES}

STOP_WORDS = {
    "with", "this", "that", "from", "your", "have", "will", "mode", "flag", "test", "file", "spec",
    "tool", "mode", "strict", "scope", "hook", "hooks", "commit", "issue", "branch", "main", "origin",
    "unrequested", "modification", "modifications", "unrelated", "runner", "release", "publish",
    "build", "docker", "setup", "buildx", "workflow", "workflows", "verification", "mechanism"
}


def normalize_name(name: str) -> str:
    return name.replace("_", "-").lower()


def is_test_file_for_in_scope(filepath: str, allowed_base_names: set) -> bool:
    lower_path = filepath.lower()
    if "test" not in lower_path and "spec" not in lower_path:
        return False

    filename = os.path.basename(filepath).lower()
    base = filename
    for pattern in ["test_", "_test", ".test", ".spec"]:
        base = base.replace(pattern, "")

    base_no_ext = os.path.splitext(base)[0]
    norm_base_no_ext = normalize_name(base_no_ext)

    for allowed in allowed_base_names:
        norm_allowed = normalize_name(allowed)
        if norm_base_no_ext in norm_allowed or norm_allowed in norm_base_no_ext:
            return True

    return False


def is_module_hierarchy_subfile(filepath: str, allowed_file_paths: set) -> bool:
    filepath_norm = os.path.normpath(filepath)
    for allowed_p in allowed_file_paths:
        allowed_p_norm = os.path.normpath(allowed_p)
        parent_dir, filename = os.path.split(allowed_p_norm)
        stem, _ = os.path.splitext(filename)

        # 1. Check if filepath is inside a folder named `stem` at parent_dir (e.g. mcp/src/config/...)
        expected_dir = os.path.normpath(os.path.join(parent_dir, stem))
        if filepath_norm.startswith(expected_dir + os.sep):
            return True

        # 2. Check if filepath is a sibling module with prefix stem (e.g. config.sub.ts or config-sub.ts)
        if parent_dir and os.path.dirname(filepath_norm) == parent_dir:
            cand_filename = os.path.basename(filepath_norm)
            if cand_filename.startswith(f"{stem}.") or cand_filename.startswith(f"{stem}-") or cand_filename.startswith(f"{stem}_"):
                return True

    return False


def check_file_imports_target(importer_path: str, target_path: str, root=None) -> bool:
    """Check if importer_path file imports target_path (or vice versa)."""
    base = os.path.abspath(root) if root else os.getcwd()
    importer_abs = os.path.join(base, importer_path)
    if not os.path.isfile(importer_abs):
        return False

    try:
        with open(importer_abs, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return False

    norm_target = os.path.normpath(target_path)
    target_dir, target_file = os.path.split(norm_target)
    target_stem, target_ext = os.path.splitext(target_file)
    importer_dir = os.path.dirname(importer_abs)

    # JS/TS relative imports: import ... from './...'
    js_imports = re.findall(r'(?:import|export|require)\s*(?:[^\'"]*?\s*from\s*)?[\(\'"]([^\'"]+)[\)\'"]', content)
    for imp in js_imports:
        if imp.startswith('.'):
            resolved = os.path.normpath(os.path.join(importer_dir, imp))
            resolved_stem, _ = os.path.splitext(resolved)
            target_base = os.path.normpath(os.path.join(base, target_dir, target_stem))
            if resolved_stem == target_base:
                return True
            if target_stem == 'index' and target_dir == resolved:
                return True

    # Python relative/absolute module imports
    py_imports = re.findall(r'(?:from|import)\s+([\.\w]+)', content)
    for imp in py_imports:
        imp_parts = imp.lstrip('.').split('.')
        target_parts = os.path.splitext(target_path)[0].split(os.sep)
        if imp_parts and imp_parts[-1] == target_stem:
            return True

    return False


def is_refactor_extraction_heuristic(filepath: str, allowed_file_paths: set, root=None) -> bool:
    """
    If a newly added/extracted file is imported by an allowed file within the same package/component tree
    (or imports an allowed file in the same package/component tree), allow it as a modular extraction.
    """
    filepath_norm = os.path.normpath(filepath)
    cand_dir = os.path.dirname(filepath_norm)

    for allowed_p in allowed_file_paths:
        allowed_p_norm = os.path.normpath(allowed_p)
        allowed_dir = os.path.dirname(allowed_p_norm)

        # Must share a package or component subtree (common parent path up to 2 directory levels)
        if cand_dir == allowed_dir or cand_dir.startswith(allowed_dir + os.sep) or allowed_dir.startswith(cand_dir + os.sep):
            # Check if allowed file imports candidate file OR candidate file imports allowed file
            if check_file_imports_target(allowed_p_norm, filepath_norm, root) or check_file_imports_target(filepath_norm, allowed_p_norm, root):
                return True

    return False


def split_camel_case(s: str) -> list:
    """Splits camelCase or PascalCase strings into lowercased component tokens."""
    return [w.lower() for w in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\b)|[0-9]+', s) if w]


def check_scope(changed_files, issue_text, root=None):
    if not issue_text:
        # If no issue text is found, we warn and pass to prevent blocking if run locally without metadata
        return True, [], []

    issue_text_lower = issue_text.lower()

    # Extract everything that looks like a file name, file path, or directory path
    path_regex = r'[a-zA-Z0-9_\-\./]+\.[a-zA-Z0-9]+'
    mentioned_files = set(re.findall(path_regex, issue_text_lower))

    # Extract directories
    dir_regex = r'[a-zA-Z0-9_\-\./]+/'
    mentioned_dirs = set(re.findall(dir_regex, issue_text_lower))

    # Extract single words/tokens
    word_regex = r'[a-zA-Z0-9_\-]+'
    raw_words = set(re.findall(word_regex, issue_text))
    mentioned_words = set()
    for w in raw_words:
        mentioned_words.add(w.lower())
        for sub_w in split_camel_case(w):
            mentioned_words.add(sub_w)

    mentioned_words = {w for w in mentioned_words if len(w) > 3 and w not in STOP_WORDS}

    allowed_base_names = set()
    for f in mentioned_files:
        filename = os.path.basename(f)
        base = os.path.splitext(filename)[0]
        allowed_base_names.add(base.lower())

    allowed_files = []
    candidates_for_pass_2 = []

    # PASS 1: Direct matches, exempt files, directory matches, test matches, token matches
    for filepath in changed_files:
        filepath_lower = filepath.lower()
        filename_lower = os.path.basename(filepath).lower()
        base_lower = os.path.splitext(filename_lower)[0]

        # 1. Exempt files
        if filename_lower in EXEMPT_FILES_LOWER:
            allowed_files.append((filepath, "Exempt configuration/readme/tooling file"))
            continue

        # 2. Exact match in mentioned files
        if any(mf in filepath_lower or filepath_lower in mf for mf in mentioned_files):
            allowed_files.append((filepath, "Exact path/pattern mentioned in issue"))
            continue

        if any(mf in filename_lower or filename_lower in mf for mf in mentioned_files):
            allowed_files.append((filepath, "Filename mentioned in issue"))
            continue

        # 3. Directory match
        is_in_mentioned_dir = False
        matched_dir = None
        for md in mentioned_dirs:
            md_clean = md.strip("/")
            if md_clean and any(part == md_clean for part in filepath_lower.split("/")):
                is_in_mentioned_dir = True
                matched_dir = md
                break
        if is_in_mentioned_dir:
            allowed_files.append((filepath, f"Located in mentioned directory: {matched_dir}"))
            continue

        # 4. Test file for an allowed file
        if is_test_file_for_in_scope(filepath, allowed_base_names):
            allowed_files.append((filepath, "Test file for an in-scope source file"))
            continue

        # 5. Base name match
        norm_base_lower = normalize_name(base_lower)
        is_base_matched = False
        for ab in allowed_base_names:
            if norm_base_lower == normalize_name(ab):
                is_base_matched = True
                break
        if not is_base_matched:
            for w in mentioned_words:
                if norm_base_lower == normalize_name(w):
                    is_base_matched = True
                    break

        if is_base_matched:
            allowed_files.append((filepath, "Base name/key token matched in issue"))
            continue

        candidates_for_pass_2.append(filepath)

    # PASS 2: Modular refactoring / sub-file extractions & import heuristics
    disallowed_files = []
    allowed_file_paths = {f[0] for f in allowed_files}

    for filepath in candidates_for_pass_2:
        # 1. Module hierarchy matching
        if is_module_hierarchy_subfile(filepath, allowed_file_paths):
            allowed_files.append((filepath, "Module hierarchy sub-file extracted from in-scope parent module"))
            allowed_file_paths.add(filepath)
            continue

        # 2. Import heuristic matching
        if is_refactor_extraction_heuristic(filepath, allowed_file_paths, root):
            allowed_files.append((filepath, "Extracted helper module imported by/importing in-scope module"))
            allowed_file_paths.add(filepath)
            continue

        disallowed_files.append(filepath)

    return len(disallowed_files) == 0, allowed_files, disallowed_files


def check_override():
    if os.environ.get("SCOPE_OVERRIDE") == "true":
        return True
    return False
