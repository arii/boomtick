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
        1. Raw JSX elements without approved design primitives or using raw style/className.
        2. Type suppressions (@ts-ignore, @ts-expect-error, unvetted any casts/annotations).
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

                # 1. Type suppressions in comments
                if ntype == "comment":
                    text = get_text(node)
                    if "@ts-ignore" in text or "@ts-expect-error" in text:
                        findings.append({
                            "type": "type_suppression",
                            "severity": "error",
                            "line": node.start_point[0] + 1,
                            "rule": "no-ts-suppression",
                            "message": f"Unvetted type suppression found: `{text.strip()}`",
                            "value": text.strip(),
                        })

                # 2. 'any' type annotation or cast
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
                elif ntype == "as_expression":
                    for child in node.children:
                        if child.type == "predefined_type" and get_text(child) == "any":
                            findings.append({
                                "type": "type_suppression",
                                "severity": "warning",
                                "line": node.start_point[0] + 1,
                                "rule": "no-any-cast",
                                "message": "Explicit `as any` type assertion detected.",
                                "value": get_text(node),
                            })

                # 3. Raw JSX element auditing
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
                        for child in opening.children:
                            if child.type == "identifier":
                                tag_name = get_text(child)
                                break

                        if tag_name in RAW_HTML_TAGS:
                            attrs_text = get_text(opening)
                            has_style = "style=" in attrs_text
                            has_raw_classes = bool(re.search(r'className=["\'].*?\b(flex|grid|p-\d|m-\d|w-|h-)\b', attrs_text))

                            if has_style or has_raw_classes or tag_name in ("div", "span"):
                                findings.append({
                                    "type": "jsx_primitive",
                                    "severity": "error" if (has_style or has_raw_classes) else "warning",
                                    "line": node.start_point[0] + 1,
                                    "rule": "use-approved-primitives",
                                    "message": f"Raw JSX `<{tag_name}>` used without approved layout primitives ({', '.join(sorted(APPROVED_DESIGN_PRIMITIVES)[:5])}...).",
                                    "value": tag_name,
                                })

                for child in node.children:
                    visit(child)

            visit(tree.root_node)

        except Exception:
            # Regexp fallback if tree-sitter fails
            raw_tags_re = r"<(?:" + "|".join(sorted(RAW_HTML_TAGS)) + r")\b"
            lines = code.splitlines()
            for idx, line in enumerate(lines):
                if "// @ts-ignore" in line or "// @ts-expect-error" in line or "/* @ts-ignore" in line:
                    findings.append({
                        "type": "type_suppression",
                        "severity": "error",
                        "line": idx + 1,
                        "rule": "no-ts-suppression",
                        "message": f"Unvetted type suppression found: `{line.strip()}`",
                        "value": line.strip(),
                    })
                if re.search(raw_tags_re, line) and ("style=" in line or "className=" in line):
                    findings.append({
                        "type": "jsx_primitive",
                        "severity": "warning",
                        "line": idx + 1,
                        "rule": "use-approved-primitives",
                        "message": f"Raw JSX element with styling found: `{line.strip()[:40]}`",
                        "value": line.strip(),
                    })

        return findings

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
