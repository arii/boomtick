"""Regression test: ast_audit must loudly mark tree-sitter downgrades (PR #1220)."""

from dev_tools.services import ast_audit
from dev_tools.services.ast_audit import ASTAuditor


def test_parser_failure_inserts_downgrade_marker_first(tmp_path, mocker, monkeypatch):
    """Tree-sitter walk failure warns and inserts the downgrade marker at findings[0]."""
    warn = mocker.patch.object(ast_audit, "log_warn")

    def _boom(self, *args, **kwargs):
        raise RuntimeError("simulated tree-sitter walk failure")

    monkeypatch.setattr("tree_sitter.Parser.parse", _boom)

    auditor = ASTAuditor(baseline_file=str(tmp_path / "baseline.json"))
    code = "// @ts-ignore\nconst x = 1;\n"
    findings = auditor.audit_file("src/Fallback.ts", code)

    assert warn.called, "expected log_warn on tree-sitter parse failure"
    assert findings, "expected regex fallback findings after downgrade"
    marker = findings[0]
    assert marker["rule"] == "ast-parser-downgrade"
    assert marker["severity"] == "warning"
    assert "no-ts-suppression" in [f["rule"] for f in findings[1:]]
