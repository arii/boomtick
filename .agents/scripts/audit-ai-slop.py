# pylint: disable=invalid-name,line-too-long,missing-docstring,no-else-return,subprocess-run-check,too-many-nested-blocks
#!/usr/bin/env python3
"""
AI Slop Audit Script

Searches codebase for banned language per audit.config.yaml
Generates actionable audit report with before/after fixes

Fail-gate (#1143): AST-based swallow-exception detection and
unreferenced shell-wrapper detection run against a checked-in
baseline (.agents/scripts/slop-baseline.json). Any NEW occurrence
fails the gate (nonzero exit); grandfathered entries stay green until
a follow-up triages them. Reseed with --update-baseline after
deliberate removals.
"""

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

BASELINE_PATH = Path(__file__).with_name("slop-baseline.json")

class AISlopAuditor:
    def __init__(self, root_dir: Optional[str] = None, config_path: str = ".agents/audit.config.yaml"):
        if root_dir is None:
            root_dir = str(Path(__file__).resolve().parent.parent.parent)
        self.root_dir = Path(root_dir)
        self.config_path = self.root_dir / config_path
        self.violations: List[Dict] = []
        self.exclude_dirs = {"node_modules", "dist", ".git", ".playwright", "test-results"}
        self.file_extensions = {".tsx", ".ts", ".md", ".jsx", ".js"}
        self.load_config()

    def load_config(self):
        if yaml is None:
            print("Warning: PyYAML unavailable; banned-term categories disabled.",
                  file=sys.stderr)
            self.config = {"categories": {}}
            return
        try:
            with open(self.config_path, 'r', encoding="utf-8") as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = {"categories": {}}

    def search_violations(self) -> None:
        """Search entire codebase for banned terms"""
        print("🔍 Scanning codebase for banned language...")

        categories = self.config.get("categories", {})
        for category, details in categories.items():
            terms = details.get("terms", [])
            fix = details.get("fix", "Fix per category")

            for term in terms:
                # Build grep pattern (case-insensitive for most terms)
                pattern = f"\\b{re.escape(term)}\\b"

                # Run grep
                try:
                    result = subprocess.run(
                        ["grep", "-r", "-n", pattern, "src/", "content/",
                         "--include=*.tsx", "--include=*.ts", "--include=*.md"],
                        capture_output=True,
                        text=True,
                        cwd=str(self.root_dir)
                    )

                    if result.stdout:
                        for line in result.stdout.strip().split("\n"):
                            if not line or "node_modules" in line:
                                continue

                            parts = line.split(":", 2)
                            if len(parts) >= 3:
                                file_path, line_num, content = parts[0], parts[1], ":".join(parts[2:])

                                self.violations.append({
                                    "file": file_path,
                                    "line": line_num,
                                    "content": content.strip(),
                                    "term": term,
                                    "category": category,
                                    "fix": fix
                                })

                except subprocess.CalledProcessError:
                    # grep exit 1 = no matches for this term: expected, keep scanning.
                    continue

    def prioritize_violations(self) -> None:
        """Sort violations by priority"""
        # Critical files (About page, landing page)
        critical_files = {
            "src/features/profile/useProfile.ts",
            "src/features/dashboard/Dashboard.tsx",
            "src/pages/Home.tsx",
            "src/pages/About.tsx"
        }

        def priority(v):
            if v["file"] in critical_files:
                return (0, v["file"], int(v["line"]))  # Priority 0 = critical
            elif "content/" in v["file"]:
                return (1, v["file"], int(v["line"]))  # Priority 1 = high
            else:
                return (2, v["file"], int(v["line"]))  # Priority 2 = normal

        self.violations.sort(key=priority)

    def generate_report(self) -> str:
        """Generate markdown audit report"""
        now = datetime.now().isoformat()

        report = f"""# AI Slop Audit Report

**Generated:** {now}
**Total Violations:** {len(self.violations)}

---

## Violations by Category

"""

        # Group by category
        by_category = {}
        for v in self.violations:
            cat = v["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(v)

        for category in sorted(by_category.keys()):
            violations = by_category[category]
            report += f"\n### {category.replace('_', ' ').title()} ({len(violations)} violations)\n\n"

            for i, v in enumerate(violations, 1):
                priority = "🔴 Critical" if "profile" in v["file"] or "dashboard" in v["file"] else "🟠 High" if "content/" in v["file"] else "🟡 Normal"
                report += f"{i}. **File:** `{v['file']}` (line {v['line']})\n"
                report += f"   **Term:** `{v['term']}`\n"
                report += f"   **Priority:** {priority}\n"
                report += f"   **Fix:** {v['fix']}\n"
                report += f"   **Context:** `...{v['content'][:100]}...`\n\n"

        # Action plan
        report += "\n---\n\n## Action Plan\n\n"
        report += f"Total violations found: {len(self.violations)}\n\n"

        # Group by priority
        critical = [v for v in self.violations if "profile" in v["file"] or "dashboard" in v["file"]]
        high = [v for v in self.violations if "content/" in v["file"] and v not in critical]

        report += f"- **Critical (About/Landing pages):** {len(critical)} violations\n"
        report += f"- **High (Content):** {len(high)} violations\n"
        report += f"- **Normal (Other):** {len(self.violations) - len(critical) - len(high)} violations\n\n"

        report += "## Next Steps\n\n"
        report += "1. Review violations by priority\n"
        report += "2. Fix critical violations first\n"
        report += "3. Run `pnpm build` to verify no breaking changes\n"
        report += "4. Commit with clear message referencing this audit\n\n"

        report += "---\n\n"
        report += "**Reference:** See `.agents/audit.config.yaml` for full standards\n"

        return report

    def run(self) -> str:
        """Execute full audit"""
        assert self.config_path.exists(), f"Config not found at {self.config_path}. Do not hardcode rules in workflows."
        self.search_violations()
        self.prioritize_violations()
        return self.generate_report()

class _SwallowVisitor(ast.NodeVisitor):
    """Collects `except ...: pass` handlers as scope-qualified signatures."""

    def __init__(self):
        self.stack: List[str] = []
        self.hits: List[str] = []

    def _push(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node):
        self._push(node)

    def visit_AsyncFunctionDef(self, node):
        self._push(node)

    def visit_ClassDef(self, node):
        self._push(node)

    def visit_ExceptHandler(self, node):
        if node.body and all(isinstance(s, ast.Pass) for s in node.body):
            scope = ".".join(self.stack) if self.stack else "<module>"
            if node.type is None:
                exc = "bare"
            elif isinstance(node.type, ast.Name):
                exc = node.type.id
            elif isinstance(node.type, ast.Tuple):
                parts = [e.id for e in node.type.elts if isinstance(e, ast.Name)]
                exc = ",".join(parts) if parts else "expr"
            else:
                exc = "expr"
            self.hits.append(f"{scope}:{exc}")
        self.generic_visit(node)


def _tracked_files(root: Path, pattern: str) -> List[str]:
    """Tracked files matching pattern; falls back to a working-tree walk."""
    try:
        res = subprocess.run(
            ["git", "ls-files", pattern],
            capture_output=True, text=True, cwd=str(root),
        )
        if res.returncode == 0 and res.stdout.strip():
            return sorted(res.stdout.split())
    except OSError as e:
        print(f"audit-ai-slop: git ls-files failed ({e}); falling back to walk", file=sys.stderr)
    return sorted(str(p.relative_to(root)) for p in root.glob(f"**/{pattern}")
                  if ".git" not in p.parts and "node_modules" not in p.parts)


def find_swallow_exceptions(root: Path) -> Dict[str, Counter]:
    """Map of py file -> Counter of swallow-exception signatures."""
    found: Dict[str, Counter] = {}
    for rel in _tracked_files(root, "*.py"):
        try:
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        visitor = _SwallowVisitor()
        visitor.visit(tree)
        if visitor.hits:
            found[rel] = Counter(visitor.hits)
    return found


def find_unreferenced_wrappers(root: Path) -> List[str]:
    """Tracked *.sh files no other tracked file references by filename."""
    scripts = _tracked_files(root, "*.sh")
    try:
        self_refs = {
            str(Path(__file__).resolve().relative_to(root)),
            str(BASELINE_PATH.resolve().relative_to(root)),
        }
    except ValueError:
        self_refs = set()
    unreferenced = []
    for rel in scripts:
        name = Path(rel).name
        try:
            res = subprocess.run(
                ["git", "grep", "-l", "-F", "-e", name, "--", "."],
                capture_output=True, text=True, cwd=str(root),
            )
            refs = [line.strip() for line in res.stdout.splitlines()
                    if line.strip() and line.strip() != rel
                    and "ai-slop-audit-" not in line
                    and line.strip() not in self_refs]
        except OSError:
            refs = ["<search-unavailable>"]
        if not refs:
            unreferenced.append(rel)
    return sorted(unreferenced)


def load_baseline() -> Dict:
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"swallow_exceptions": {}, "unreferenced_wrappers": []}


def gate_failures(root: Path, baseline: Dict) -> List[str]:
    """New (non-baselined) swallow-exceptions and wrappers; empty = pass."""
    failures = []
    base_swallow = baseline.get("swallow_exceptions", {})
    for rel, counter in find_swallow_exceptions(root).items():
        base = Counter(base_swallow.get(rel, {}))
        for sig, count in sorted(counter.items()):
            if count > base.get(sig, 0):
                failures.append(
                    f"swallow-exception {rel} [{sig}] x{count} "
                    f"(baseline x{base.get(sig, 0)})")
    base_wrappers = set(baseline.get("unreferenced_wrappers", []))
    for rel in find_unreferenced_wrappers(root):
        if rel not in base_wrappers:
            failures.append(f"unreferenced-wrapper {rel}")
    return failures


def write_baseline(root: Path) -> None:
    baseline = {
        "version": 1,
        "note": ("#1143 slop fail-gate ratchet: grandfathered hits stay "
                 "green until a follow-up triages them; any NEW entry "
                 "fails the gate. Reseed with --update-baseline."),
        "swallow_exceptions": {
            rel: dict(sorted(counter.items()))
            for rel, counter in sorted(find_swallow_exceptions(root).items())},
        "unreferenced_wrappers": find_unreferenced_wrappers(root),
    }
    BASELINE_PATH.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    print(f"Baseline wrote {len(baseline['swallow_exceptions'])} files, "
          f"{len(baseline['unreferenced_wrappers'])} wrappers -> {BASELINE_PATH}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AI slop audit + fail-gate (#1143)")
    parser.add_argument("--update-baseline", action="store_true",
                        help="Reseed slop-baseline.json from the current tree")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent.parent.parent
    if args.update_baseline:
        write_baseline(root)
        return 0

    auditor = AISlopAuditor(root_dir=str(root))
    report = auditor.run()

    # Output report
    print(report)

    # Save to file
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = auditor.root_dir / ".agents/workflows"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"ai-slop-audit-{timestamp}.md"
    output_file.write_text(report)

    print(f"\n✅ Report saved to: {output_file}")
    print(f"📊 Found {len(auditor.violations)} violations")

    failures = gate_failures(root, load_baseline())
    if failures:
        print("\n🚨 Slop fail-gate BLOCKED (#1143):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\n✅ Slop fail-gate passed (#1143): "
          "no new swallow-exceptions or unreferenced wrappers.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
