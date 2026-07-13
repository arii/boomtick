# pylint: disable=missing-docstring
import json

from dev_tools.models import AIFullReview, AIReviewIssue, AISynthesisReview
from dev_tools.services.ai_service import validate_with_model


def test_validate_ai_review_issue_success():
    data = {
        "id": "1",
        "severity": "error",
        "comment": "test comment",
        "confidence": "high",
        "line": 10,
    }
    parsed, err = validate_with_model(data, AIReviewIssue)
    assert err is None
    assert parsed["comment"] == "test comment"
    assert parsed["severity"] == "error"


def test_validate_ai_review_issue_alternative_field():
    data = {"severity": "warn", "issue": "test issue", "confidence": "medium"}
    parsed, err = validate_with_model(data, AIReviewIssue)
    assert err is None
    assert parsed["issue"] == "test issue"


def test_validate_ai_review_issue_failure_missing_fields():
    data = {
        "severity": "error",
        "confidence": "high",
        # missing both issue and comment
    }
    parsed, err = validate_with_model(data, AIReviewIssue)
    assert parsed is None
    assert "issue" in err or "comment" in err


def test_validate_ai_review_issue_failure_invalid_enum():
    data = {
        "severity": "critical",  # invalid
        "comment": "test",
        "confidence": "very high",  # invalid
    }
    parsed, err = validate_with_model(data, AIReviewIssue)
    assert parsed is None
    assert "severity" in err
    assert "confidence" in err


def test_validate_full_review_success():
    data = {
        "file_reviews": [
            {
                "file": "test.py",
                "issues": [{"severity": "info", "comment": "nit", "confidence": "low", "line": 1}],
                "verdict": "ok",
            }
        ],
        "reviewComment": "Looks good",
        "labels": ["lgtm"],
        "recommendation": "Approved",
    }
    parsed, err = validate_with_model(data, AIFullReview)
    assert err is None
    assert len(parsed["file_reviews"]) == 1
    assert parsed["recommendation"] == "Approved"


def test_validate_synthesis_review_double_encoding():
    # Simulate double stringified JSON
    inner_json = json.dumps({"reviewComment": "Summary", "labels": [], "recommendation": "Not Approved"})
    double_encoded = json.dumps(inner_json)

    parsed, err = validate_with_model(double_encoded, AISynthesisReview)
    assert err is None
    assert parsed["recommendation"] == "Not Approved"


def test_validate_with_model_detailed_errors():
    data = {
        "file_reviews": [
            {
                "file": "test.py",
                "issues": [
                    {
                        "severity": "invalid",
                        "confidence": "low",
                        # missing issue/comment
                    }
                ],
                "verdict": "ok",
            }
        ],
        "reviewComment": "oops",
        "labels": [],
        "recommendation": "Approved",
    }
    parsed, err = validate_with_model(data, AIFullReview)
    assert parsed is None
    # Check that error message contains the path to the error
    assert "file_reviews -> 0 -> issues -> 0 -> severity" in err
    assert "file_reviews -> 0 -> issues -> 0" in err
