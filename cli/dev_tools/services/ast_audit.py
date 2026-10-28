# pylint: disable=missing-docstring,import-outside-toplevel,line-too-long
import json
import os
import re
from typing import Any, Dict, List, Set

APPROVED_DESIGN_PRIMITIVES: Set[str] = {
    "Box",
    "Stack",
    "HStack",
    "VStack",
    "Grid",
    "Flex",
    "Container",
    "Text",
    "Heading",
    "Button",
    "Icon",
    "Image",
    "Link",
    "Card",
    "Badge",
    "Spinner",
    "Divider",
}

RAW_HTML_TAGS: Set[str] = {
    "div",
    "span",
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "button",
    "a",
    "img",
    "section",
    "article",
    "main",
    "header",
    "footer",
    "ul",
    "ol",
    "li",
}

TYPOGRAPHY_HTML_TAGS: Set[str] = {"p", "h1", "h2", "h3", "h4", "h5", "h6"}

# Regex for placeholder comments
PLACEHOLDER_COMMENT_RE = re.compile(
    r"\b(TODO|FIXME|STUB|HACK|AI scaffolding)\b(?::|\s)", re.IGNORECASE
)

# Regex for AI scaffolding / mock stubs
MOCK_STUB_NAME_RE = re.compile(
    r"\b(mockData|mockStub|stubData|dummyData|tempStub|mockResponse|mockUser|mockList|dummyUser|stubResponse)\b"
)


class ASTAuditor:
    def __init__(self, baseline_file: str = "audit-baseline.json"):
        self.baseline_file = baseline_file
        self.baseline: Dict[str, Any] = self._load_baseline()

    def _load_baseline(self) -> Dict[str, Any]:
        if os.path.exists(self.baseline_file):
            try:
                with open(self.baseline_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_baseline(self, new_baseline: Dict[str, Any]) -> None:
        with open(self.baseline_file, "w", encoding="utf-8") as f:
            json.dump(new_baseline, f, indent=2)

    def _inspect_comment_node(self, node, get_text) -> Any:
        text = get_text(node).strip()
        if "@ts-ignore" in text or "@ts-expect-error" in text:
            return {
                "type": "type_suppression",
                "severity": "error",
                "line": node.start_point[0] + 1,
                "rule": "no-ts-suppression",
                "message": f"Unvetted type suppression found: `{text}`",
                "value": text,
            }
        if PLACEHOLDER_COMMENT_RE.search(text):
            return {
                "type": "dead_code",
                "severity": "warning",
                "line": node.start_point[0] + 1,
                "rule": "no-placeholder-comment",
                "message": f"Placeholder comment detected: `{text}`",
                "value": text,
            }
        return None

    def _inspect_type_node(self, node, get_text) -> Any:
        ntype = node.type
        if ntype == "type_annotation":
            for child in node.children:
                if child.type == "predefined_type" and get_text(child) == "any":
                    return {
                        "type": "type_suppression",
                        "severity": "warning",
                        "line": node.start_point[0] + 1,
                        "rule": "no-explicit-any",
                        "message": "Explicit `any` type annotation detected.",
                        "value": get_text(node),
                    }
        elif ntype in ("as_expression", "type_assertion"):
            for child in node.children:
                if child.type == "predefined_type" and get_text(child) == "any":
                    return {
                        "type": "type_suppression",
                        "severity": "warning",
                        "line": node.start_point[0] + 1,
                        "rule": "no-any-cast",
                        "message": "Explicit `any` type assertion detected.",
                        "value": get_text(node),
                    }
        return None

    def _inspect_declaration_node(self, node, get_text) -> Any:
        if node.type not in ("variable_declarator", "function_declaration"):
            return None
        name_node = next((c for c in node.children if c.type == "identifier"), None)
        if name_node:
            ident_name = get_text(name_node)
            if MOCK_STUB_NAME_RE.search(ident_name):
                return {
                    "type": "ai_scaffolding",
                    "severity": "warning",
                    "line": name_node.start_point[0] + 1,
                    "rule": "no-ai-scaffolding",
                    "message": f"Unused mock stub or AI scaffolding detected: `{ident_name}`.",
                    "value": ident_name,
                }
        return None

    def _inspect_jsx_node(self, node, get_text) -> Any:
        ntype = node.type
        if ntype not in ("jsx_element", "jsx_self_closing_element"):
            return None

        opening = node
        if ntype == "jsx_element":
            opening = next((c for c in node.children if c.type == "jsx_opening_element"), None)

        if not opening:
            return None

        tag_name = ""
        has_style = False
        has_classname = False

        for child in opening.children:
            if child.type == "identifier":
                tag_name = get_text(child)
            elif child.type == "jsx_attribute":
                attr_name = next(
                    (get_text(ac) for ac in child.children if ac.type == "property_identifier"), ""
                )
                if attr_name == "style":
                    has_style = True
                elif attr_name == "className":
                    has_classname = True

        if tag_name in TYPOGRAPHY_HTML_TAGS:
            return {
                "type": "typography_token",
                "severity": "warning",
                "line": node.start_point[0] + 1,
                "rule": "use-typography-tokens",
                "message": (
                    f"Raw HTML typography `<{tag_name}>` bypasses shared typography primitives"
                    " (<Text />, <Heading />, etc.)."
                ),
                "value": tag_name,
            }

        if tag_name in RAW_HTML_TAGS:
            if has_style:
                return {
                    "type": "jsx_primitive",
                    "severity": "error",
                    "line": node.start_point[0] + 1,
                    "rule": "use-approved-primitives",
                    "message": f"Raw JSX `<{tag_name}>` with inline `style` bypasses design primitives.",
                    "value": tag_name,
                }
            if has_classname:
                return {
                    "type": "jsx_primitive",
                    "severity": "error" if tag_name in ("div", "span") else "warning",
                    "line": node.start_point[0] + 1,
                    "rule": "use-approved-primitives",
                    "message": (
                        f"Raw JSX `<{tag_name}>` with `className` bypasses shared layout primitives"
                        " (<Box />, <Stack />, <Grid />, etc.)."
                    ),
                    "value": tag_name,
                }
        return None

    def _fallback_regex_audit(self, code: str) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        lines = code.splitlines()
        raw_tags_re = r"<(?:" + "|".join(sorted(RAW_HTML_TAGS)) + r")\b"
        typo_tags_re = r"<(?:" + "|".join(sorted(TYPOGRAPHY_HTML_TAGS)) + r")\b"
        for idx, line in enumerate(lines):
            line_str = line.strip()
            if "// @ts-ignore" in line_str or "// @ts-expect-error" in line_str or "/* @ts-ignore" in line_str:
                findings.append({
                    "type": "type_suppression",
                    "severity": "error",
                    "line": idx + 1,
                    "rule": "no-ts-suppression",
                    "message": f"Unvetted type suppression found: `{line_str}`",
                    "value": line_str,
                })
            elif PLACEHOLDER_COMMENT_RE.search(line_str):
                findings.append({
                    "type": "dead_code",
                    "severity": "warning",
                    "line": idx + 1,
                    "rule": "no-placeholder-comment",
                    "message": f"Placeholder comment detected: `{line_str}`",
                    "value": line_str,
                })
            if re.search(typo_tags_re, line):
                findings.append({
                    "type": "typography_token",
                    "severity": "warning",
                    "line": idx + 1,
                    "rule": "use-typography-tokens",
                    "message": f"Raw HTML typography tag found: `{line_str[:40]}`",
                    "value": line_str,
                })
            elif re.search(raw_tags_re, line) and ("style=" in line or "className=" in line):
                findings.append({
                    "type": "jsx_primitive",
                    "severity": "warning",
                    "line": idx + 1,
                    "rule": "use-approved-primitives",
                    "message": f"Raw JSX element with styling found: `{line_str[:40]}`",
                    "value": line_str,
                })
        return findings

    def audit_file(self, filepath: str, code: str) -> List[Dict[str, Any]]:
        """
        Parses TypeScript/TSX code using tree-sitter AST to audit:
        1. Design System / Token Bypasses: Flag raw JSX (<div style="...">, <div className="...">)
           that bypasses shared layout primitives.
        2. Type Bypasses: Flag // @ts-ignore, // @ts-expect-error, or any casts against an approved baseline inventory.
        3. Dead Code / AI Scaffolding: Detect placeholder comments (// TODO: implement later)
           or unused mock stubs left by autonomous agents.
        """
        findings: List[Dict[str, Any]] = []

        is_ts = filepath.endswith((".ts", ".tsx", ".js", ".jsx"))
        if not is_ts or not code.strip():
            return findings

        try:
            import tree_sitter
            import tree_sitter_typescript as tsts

            ts_lang = tsts.language_tsx() if filepath.endswith("x") else tsts.language_typescript()
            lang = tree_sitter.Language(ts_lang)
            parser = tree_sitter.Parser(lang)
            code_bytes = code.encode("utf-8")
            tree = parser.parse(code_bytes)

            def get_text(node) -> str:
                return code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")

            def visit(node):
                ntype = node.type
                finding = None
                if ntype == "comment":
                    finding = self._inspect_comment_node(node, get_text)
                elif ntype in ("type_annotation", "as_expression", "type_assertion"):
                    finding = self._inspect_type_node(node, get_text)
                elif ntype in ("variable_declarator", "function_declaration"):
                    finding = self._inspect_declaration_node(node, get_text)
                elif ntype in ("jsx_element", "jsx_self_closing_element"):
                    finding = self._inspect_jsx_node(node, get_text)

                if finding:
                    findings.append(finding)

                for child in node.children:
                    visit(child)

            visit(tree.root_node)

        except Exception:
            findings = self._fallback_regex_audit(code)

        return findings

    def audit_directory(self, dirpath: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Recursively audits a directory for TS/TSX files.
        """
        dir_findings: Dict[str, List[Dict[str, Any]]] = {}
        if not os.path.isdir(dirpath):
            return dir_findings

        for root, dirs, files in os.walk(dirpath):
            # Exclude node_modules, .git, dist, .venv
            dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "dist", "build", ".venv", "__pycache__")]
            for file in files:
                if file.endswith((".ts", ".tsx", ".js", ".jsx")):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            code = f.read()
                        f_findings = self.audit_file(filepath, code)
                        if f_findings:
                            dir_findings[filepath] = f_findings
                    except Exception:
                        pass

        return dir_findings

    def audit_diff_against_baseline(self, files_data: Dict[str, str]) -> Dict[str, Any]:
        """
        Audits provided changed files against the audit baseline.
        Rejects diffs that introduce new unvetted type suppressions or design primitive violations.
        """
        new_findings: Dict[str, List[Dict[str, Any]]] = {}
        total_violations = 0

        baseline_suppressions = self.baseline.get("suppressions", {})

        for fp, code in files_data.items():
            file_findings = self.audit_file(fp, code)
            unvetted = []

            known_baseline_lines = set(baseline_suppressions.get(fp, []))

            for f in file_findings:
                # Reject if finding line is not in approved baseline
                if f["line"] not in known_baseline_lines:
                    unvetted.append(f)

            if unvetted:
                new_findings[fp] = unvetted
                total_violations += len(unvetted)

        return {
            "status": "success" if total_violations == 0 else "rejected",
            "total_violations": total_violations,
            "findings": new_findings,
        }
