import json
import pytest
from dev_tools.services.vector_store import VectorStore
from dev_tools.services.ast_audit import ASTAuditor
from dev_tools.orchestrator import Orchestrator


def test_vector_store_ast_chunking_and_bm25(tmp_path):
    db_dir = str(tmp_path / "chroma_db")
    vs = VectorStore(persist_directory=db_dir)

    ts_code = """
interface User {
    id: string;
    name: string;
}

export function getUser(id: string): User {
    return { id, name: "Alice" };
}

export const UserCard = ({ user }: { user: User }) => {
    return <div className="card">{user.name}</div>;
};
"""
    chunks = vs.chunk_code_ast(ts_code, "src/components/User.tsx")
    assert len(chunks) >= 2
    assert any("interface User" in c["content"] for c in chunks)
    assert any("function getUser" in c["content"] or "getUser" in c["content"] for c in chunks)

    # Test incremental indexing and BM25 index
    ids = vs.add_file_incremental("src/components/User.tsx", ts_code)
    assert len(ids) == len(chunks)

    file_map = {"src/components/User.tsx": ts_code}
    vs.index_files(file_map)

    if vs.is_available():
        results = vs.query("getUser Alice", n_results=2, hybrid=True)
        assert len(results) > 0


def test_ast_auditor_type_suppression_and_jsx_primitives(tmp_path):
    auditor = ASTAuditor(baseline_file=str(tmp_path / "audit-baseline.json"))

    bad_code = """
// @ts-ignore
const x: any = 10;

export function BadComponent() {
    return (
        <div className="flex p-4" style={{ color: "red" }}>
            <span>Raw text</span>
        </div>
    );
}
"""
    findings = auditor.audit_file("src/BadComponent.tsx", bad_code)
    assert any(f["rule"] == "no-ts-suppression" for f in findings)
    assert any(f["rule"] == "no-explicit-any" for f in findings)
    assert any(f["rule"] == "use-approved-primitives" for f in findings)

    # Audit diff against baseline
    res = auditor.audit_diff_against_baseline({"src/BadComponent.tsx": bad_code})
    assert res["status"] == "rejected"
    assert res["total_violations"] > 0


def test_orchestrator_preflight(mocker):
    orch = Orchestrator()
    mocker.patch.object(orch, "get_audit_results", return_value={"violations": {}})
    mocker.patch.object(orch, "detect_conflicts", return_value={})
    mocker.patch("dev_tools.orchestrator.run_command", return_value=mocker.MagicMock(returncode=0, stdout="clean"))

    res = orch.run_preflight(base_branch="main")
    assert res["status"] == "success"
    assert "audit" in res
    assert "lint" in res
    assert "overlaps" in res
    assert "merge_simulation" in res
