# pylint: disable=missing-docstring,redefined-outer-name
import pytest
from dev_tools.orchestrator import Orchestrator


@pytest.fixture
def orchestrator():
    return Orchestrator()


def test_parse_comment_conflict_resolve(orchestrator):
    res = orchestrator.parse_comment("@conflict-resolve please", "CONTRIBUTOR")
    assert res["conflict_resolve"] is True
    assert res["update_snapshots"] is False
    assert res["ai_chatops"] is False
    assert res["jules_fix_ci"] is False


def test_parse_comment_update_snapshots(orchestrator):
    res = orchestrator.parse_comment("Hey @update-snapshots", "CONTRIBUTOR")
    assert res["conflict_resolve"] is False
    assert res["update_snapshots"] is True
    assert res["ai_chatops"] is False
    assert res["jules_fix_ci"] is False


def test_parse_comment_ai_fix(orchestrator):
    res = orchestrator.parse_comment("/ai-fix this", "CONTRIBUTOR")
    assert res["conflict_resolve"] is False
    assert res["update_snapshots"] is False
    assert res["ai_chatops"] is True
    assert res["jules_fix_ci"] is False


def test_parse_comment_ai_review(orchestrator):
    res = orchestrator.parse_comment("/ai-review please", "CONTRIBUTOR")
    assert res["conflict_resolve"] is False
    assert res["update_snapshots"] is False
    assert res["ai_chatops"] is True
    assert res["jules_fix_ci"] is False


def test_parse_comment_jules_fix_ci_owner(orchestrator):
    res = orchestrator.parse_comment("@jules-fix-ci help", "OWNER")
    assert res["jules_fix_ci"] is True


def test_parse_comment_jules_fix_ci_member(orchestrator):
    res = orchestrator.parse_comment("@jules-fix-ci help", "MEMBER")
    assert res["jules_fix_ci"] is True


def test_parse_comment_jules_fix_ci_collaborator(orchestrator):
    res = orchestrator.parse_comment("@jules-fix-ci help", "COLLABORATOR")
    assert res["jules_fix_ci"] is True


def test_parse_comment_jules_fix_ci_none(orchestrator):
    res = orchestrator.parse_comment("@jules-fix-ci help", "CONTRIBUTOR")
    assert res["jules_fix_ci"] is False


def test_parse_comment_multiple(orchestrator):
    res = orchestrator.parse_comment("@conflict-resolve and @update-snapshots", "CONTRIBUTOR")
    assert res["conflict_resolve"] is True
    assert res["update_snapshots"] is True
    assert res["ai_chatops"] is False
    assert res["jules_fix_ci"] is False


def test_parse_comment_boundary_false_positive(orchestrator):
    # Should NOT match when attached to a word
    res = orchestrator.parse_comment("foo@conflict-resolve", "OWNER")
    assert res["conflict_resolve"] is False

    res = orchestrator.parse_comment("bar/ai-fix", "OWNER")
    assert res["ai_chatops"] is False


def test_parse_comment_boundary_start_end(orchestrator):
    # Should match at start or end of string
    res = orchestrator.parse_comment("@conflict-resolve", "OWNER")
    assert res["conflict_resolve"] is True

    res = orchestrator.parse_comment("/ai-review", "OWNER")
    assert res["ai_chatops"] is True


def test_parse_comment_boundary_punctuation(orchestrator):
    # Should match when surrounded by punctuation
    res = orchestrator.parse_comment("(@conflict-resolve)", "OWNER")
    assert res["conflict_resolve"] is True

    res = orchestrator.parse_comment("Done /ai-fix.", "OWNER")
    assert res["ai_chatops"] is True
