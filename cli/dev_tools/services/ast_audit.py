# pylint: disable=missing-docstring,import-outside-toplevel,line-too-long
import json
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

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

        is_ts = filepath.endswith(".ts") or filepath.endswith(".tsx") or filepath.endswith(".js") or filepath.endswith(".jsx")
        if not is_ts or not code.strip():
            return findings

        try:
            import tree_sitter
            import tree_sitter_typescript as tsts

            lang = tree_sitter.Language(tsts.language_tsx() if filepath.endswith("x") else tsts.language_typescript())
            parser = tree_sitter.Parser(lang)
            code_bytes = code.encode("utf-8")
            tree = parser.parse(code_bytes)

            def get_text(node) -> str:
                return code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")

            def visit(node):
                ntype = node.type

                # 1. Comment inspection: Type suppressions & Placeholder comments / AI scaffolding
                if ntype == "comment":
                    text = get_text(node).strip()
                    if "@ts-ignore" in text or "@ts-expect-error" in text:
                        findings.append({
                            "type": "type_suppression",
                            "severity": "error",
                            "line": node.start_point[0] + 1,
                            "rule": "no-ts-suppression",
                            "message": f"Unvetted type suppression found: `{text}`",
                            "value": text,
                        })
                    elif PLACEHOLDER_COMMENT_RE.search(text):
                        findings.append({
                            "type": "dead_code",
                            "severity": "warning",
                            "line": node.start_point[0] + 1,
                            "rule": "no-placeholder-comment",
                            "message": f"Placeholder comment detected: `{text}`",
                            "value": text,
                        })

                # 2. Type annotation / cast checks ('any')
                elif ntype == "type_annotation":
                    for child in node.children:
                        if child.type == "predefined_type" and get_text(child) == "any":
                            findings.append({
                                "type": "type_suppression",
                                "severity": "warning",
                                "line": node.start_point[0] + 1,
                                "rule": "no-explicit-any",
                                "message": "Explicit `any` type annotation detected.",
                                "value": get_text(node),
                            })
                elif ntype in ("as_expression", "type_assertion"):
                    for child in node.children:
                        if child.type == "predefined_type" and get_text(child) == "any":
                            findings.append({
                                "type": "type_suppression",
                                "severity": "warning",
                                "line": node.start_point[0] + 1,
                                "rule": "no-any-cast",
                                "message": "Explicit `any` type assertion detected.",
                                "value": get_text(node),
                            })

                # 3. AI Scaffolding / Unused Mock Stubs
                elif ntype in ("variable_declarator", "function_declaration"):
                    name_node = None
                    for child in node.children:
                        if child.type == "identifier":
                            name_node = child
                            break
                    if name_node:
                        ident_name = get_text(name_node)
                        if MOCK_STUB_NAME_RE.search(ident_name):
                            findings.append({
                                "type": "ai_scaffolding",
                                "severity": "warning",
                                "line": name_node.start_point[0] + 1,
                                "rule": "no-ai-scaffolding",
                                "message": f"Unused mock stub or AI scaffolding detected: `{ident_name}`.",
                                "value": ident_name,
                            })

                # 4. Raw JSX element auditing (Design System / Token Bypasses)
                elif ntype in ("jsx_element", "jsx_self_closing_element"):
                    opening = None
                    if ntype == "jsx_element":
                        for child in node.children:
                            if child.type == "jsx_opening_element":
                                opening = child
                                break
                    else:
                        opening = node

                    if opening:
                        tag_name = ""
                        has_style_attr = False
                        has_classname_attr = False

                        for child in opening.children:
                            if child.type == "identifier":
                                tag_name = get_text(child)
                            elif child.type == "jsx_attribute":
                                attr_name = ""
                                for attr_child in child.children:
                                    if attr_child.type == "property_identifier":
                                        attr_name = get_text(attr_child)
                                        break
                                if attr_name == "style":
                                    has_style_attr = True
                                elif attr_name == "className":
                                    has_classname_attr = True

                        if tag_name in RAW_HTML_TAGS:
                            if has_style_attr:
                                findings.append({
                                    "type": "jsx_primitive",
                                    "severity": "error",
                                    "line": node.start_point[0] + 1,
                                    "rule": "use-approved-primitives",
                                    "message": f"Raw JSX `<{tag_name}>` with inline `style` bypasses design primitives.",
                                    "value": tag_name,
                                })
                            elif has_classname_attr:
                                findings.append({
                                    "type": "jsx_primitive",
                                    "severity": "error" if tag_name in ("div", "span") else "warning",
                                    "line": node.start_point[0] + 1,
                                    "rule": "use-approved-primitives",
                                    "message": f"Raw JSX `<{tag_name}>` with `className` bypasses shared layout primitives (<Box />, <Stack />, <Grid />, etc.).",
                                    "value": tag_name,
                                })

                for child in node.children:
                    visit(child)

            visit(tree.root_node)

        except Exception:
            # Fallback regex scanner if tree-sitter fails
            lines = code.splitlines()
            raw_tags_re = r"<(?:" + "|".join(sorted(RAW_HTML_TAGS)) + r")\b"
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
                if re.search(raw_tags_re, line) and ("style=" in line or "className=" in line):
                    findings.append({
                        "type": "jsx_primitive",
                        "severity": "warning",
                        "line": idx + 1,
                        "rule": "use-approved-primitives",
                        "message": f"Raw JSX element with styling found: `{line_str[:40]}`",
                        "value": line_str,
                    })

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
