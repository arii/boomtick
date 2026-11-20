"""Live support APIs retained while orphan wrappers are removed."""

import json

from dev_tools.orchestrator import Orchestrator
from dev_tools.services.ast_audit import ASTAuditor
from dev_tools.services.context_builder import ContextBuilder
from dev_tools.services.worktrees import WARM_LINK_DIRS


def test_audit_baseline_still_loads(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"kept": ["existing-rule"]}))
    assert ASTAuditor(str(path)).baseline == {"kept": ["existing-rule"]}
    assert ASTAuditor(str(tmp_path / "missing.json")).baseline == {}


def test_live_context_and_aggregation_apis_remain():
    assert callable(ContextBuilder.build_structured_context)
    assert callable(ContextBuilder.build_markdown_context)
    assert callable(Orchestrator.generate_aggregation_workflow)
    # Historical/manual intent is still documented for this distinct method.
    assert callable(Orchestrator.generate_aggregate_prs_workflow)
    assert callable(Orchestrator.run_workflow_graph)


def test_warm_link_configuration_unchanged():
    assert WARM_LINK_DIRS == ("node_modules", ".venv", "venv", ".agents/skills")
