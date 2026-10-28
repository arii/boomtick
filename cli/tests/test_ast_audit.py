"""Unit tests for ASTAuditor (Tree-sitter semantic AST linting & anti-slop audits)."""
import importlib.util

import pytest
from dev_tools.services.ast_audit import ASTAuditor
from dev_tools.orchestrator import Orchestrator

HAS_TREE_SITTER = (
    importlib.util.find_spec("tree_sitter") is not None
    and importlib.util.find_spec("tree_sitter_typescript") is not None
)


@pytest.mark.skipif(not HAS_TREE_SITTER, reason="tree-sitter or tree-sitter-typescript not installed")
def test_typography_token_bypasses(tmp_path):
    """Test detection of raw HTML typography elements bypassing design typography tokens."""
    auditor = ASTAuditor(baseline_file=str(tmp_path / "baseline.json"))

    code = """
export function BadTypography() {
    return (
        <div>
            <h1>Header Title</h1>
            <p>Body paragraph</p>
        </div>
    );
}
"""
    findings = auditor.audit_file("src/BadTypography.tsx", code)
    rules = [f["rule"] for f in findings]
    assert "use-typography-tokens" in rules
    assert len(findings) >= 2


@pytest.mark.skipif(not HAS_TREE_SITTER, reason="tree-sitter or tree-sitter-typescript not installed")
def test_design_system_and_token_bypasses(tmp_path):
    """Test detection of raw JSX tags with inline style or className bypassing layout primitives."""
    auditor = ASTAuditor(baseline_file=str(tmp_path / "baseline.json"))

    code = """
export function BadLayout() {
    return (
        <div style={{ padding: "10px" }} className="flex col">
            <span className="bold-text">Title</span>
            <p style={{ color: "red" }}>Paragraph</p>
        </div>
    );
}
"""
    findings = auditor.audit_file("src/BadLayout.tsx", code)
    rules = [f["rule"] for f in findings]
    assert "use-approved-primitives" in rules
    assert len(findings) >= 2


@pytest.mark.skipif(not HAS_TREE_SITTER, reason="tree-sitter or tree-sitter-typescript not installed")
def test_type_bypasses_and_baseline_inventory(tmp_path):
    """Test detection of @ts-ignore, @ts-expect-error, and explicit any casts against baseline."""
    auditor = ASTAuditor(baseline_file=str(tmp_path / "baseline.json"))

    code = """
// @ts-ignore
const x: any = 10;

// @ts-expect-error
const y = x as any;
"""
    findings = auditor.audit_file("src/TypeCheck.ts", code)
    rules = [f["rule"] for f in findings]
    assert "no-ts-suppression" in rules
    assert "no-explicit-any" in rules or "no-any-cast" in rules

    # Test baseline rejection for new unvetted type suppressions
    res = auditor.audit_diff_against_baseline({"src/TypeCheck.ts": code})
    assert res["status"] == "rejected"
    assert res["total_violations"] > 0


@pytest.mark.skipif(not HAS_TREE_SITTER, reason="tree-sitter or tree-sitter-typescript not installed")
def test_dead_code_and_ai_scaffolding(tmp_path):
    """Test detection of placeholder comments and AI scaffolding mock stubs."""
    auditor = ASTAuditor(baseline_file=str(tmp_path / "baseline.json"))

    code = """
// TODO: implement later
/* FIXME: AI scaffolding stub */

const mockData = { id: 1, name: "test" };
function getStubResponse() {
    return null;
}
"""
    findings = auditor.audit_file("src/Scaffolding.ts", code)
    rules = [f["rule"] for f in findings]
    assert "no-placeholder-comment" in rules
    assert "no-ai-scaffolding" in rules


@pytest.mark.skipif(not HAS_TREE_SITTER, reason="tree-sitter or tree-sitter-typescript not installed")
def test_audit_directory(tmp_path):
    """Test recursive directory auditing with ASTAuditor."""
    auditor = ASTAuditor(baseline_file=str(tmp_path / "baseline.json"))

    subdir = tmp_path / "components"
    subdir.mkdir()

    file_a = subdir / "ComponentA.tsx"
    file_a.write_text("// TODO: implement later\nexport const mockData = {};\n", encoding="utf-8")

    file_b = subdir / "ComponentB.tsx"
    file_b.write_text("export function Clean() { return <button>Click</button>; }\n", encoding="utf-8")

    results = auditor.audit_directory(str(subdir))
    assert str(file_a) in results
    assert str(file_b) not in results


def test_orchestrator_get_audit_results_directory_integration(tmp_path, mocker):
    """Test Orchestrator.get_audit_results with directory target integration."""
    orch = Orchestrator()

    subdir = tmp_path / "features"
    subdir.mkdir()

    feature_file = subdir / "Feature.tsx"
    feature_file.write_text("""
// @ts-ignore
const mockData = [];
export function Feature() {
    return <div style={{ margin: 0 }}>Feature</div>;
}
""", encoding="utf-8")

    mocker.patch.object(orch, "_resolve_antipatterns_script", return_value="scripts/detect-antipatterns.mjs")
    mocker.patch("dev_tools.orchestrator.run_command", return_value=mocker.MagicMock(
        returncode=0,
        stdout='{"violations": {}, "config": {}}'
    ))

    res = orch.get_audit_results(targets=[str(subdir)])
    assert "violations" in res
    rel_path = str(feature_file)
    assert any(rel_path in key or "Feature.tsx" in key for key in res["violations"].keys())
